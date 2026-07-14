"""The framework-agnostic GSI receiver.

This is the *domain* half of Module 5: it takes a raw payload dict, authenticates
it, parses it into a :class:`~ai_caster.gsi.models.GameState`, updates the match
state store, and publishes a :class:`GSIStateUpdated` event. It knows nothing
about HTTP, which is what makes it fully unit-testable without a socket. The
FastAPI transport (:mod:`ai_caster.gsi.server`) is a thin adapter over this.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from pydantic import ValidationError

from ai_caster.core.events import EventBus, GSIConnectionChanged, GSIStateUpdated
from ai_caster.core.logging import get_logger
from ai_caster.gsi.models import GameState
from ai_caster.match.state import DataSource, MatchSnapshot, MatchStateStore

_log = get_logger("gsi.receiver")


class GSIAuthError(Exception):
    """Raised when a payload's auth token does not match the configured token."""


class GSIReceiver:
    """Ingests GSI payloads and fans them out to the rest of the app.

    Parameters
    ----------
    event_bus:
        Bus to publish :class:`GSIStateUpdated` / :class:`GSIConnectionChanged`.
    match_store:
        Store updated with each parsed snapshot. Created if not supplied.
    auth_token:
        Expected shared secret. Empty string disables auth checking.
    require_auth:
        When ``True`` a missing/mismatched token raises :class:`GSIAuthError`.
    """

    def __init__(
        self,
        event_bus: EventBus,
        match_store: MatchStateStore | None = None,
        *,
        auth_token: str = "",
        require_auth: bool = True,
    ) -> None:
        self._bus = event_bus
        self._store = match_store or MatchStateStore()
        self._auth_token = auth_token
        self._require_auth = require_auth
        self._lock = threading.Lock()
        self._last_payload_at: datetime | None = None
        self._connected = False
        self._payload_count = 0

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #
    @property
    def match_store(self) -> MatchStateStore:
        return self._store

    @property
    def payload_count(self) -> int:
        return self._payload_count

    @property
    def last_payload_at(self) -> datetime | None:
        return self._last_payload_at

    def update_auth(self, auth_token: str, require_auth: bool) -> None:
        """Apply new auth configuration (e.g. after a settings change)."""
        with self._lock:
            self._auth_token = auth_token
            self._require_auth = require_auth

    # ------------------------------------------------------------------ #
    # Core
    # ------------------------------------------------------------------ #
    def handle_payload(self, payload: dict) -> GameState:
        """Authenticate, parse and dispatch a raw GSI payload.

        Raises
        ------
        GSIAuthError
            If auth is required and the token is missing or wrong.
        pydantic.ValidationError
            If the payload cannot be parsed into a :class:`GameState`.
        """
        self._authenticate(payload)

        try:
            state = GameState.model_validate(payload)
        except ValidationError:
            _log.exception("Failed to parse GSI payload")
            raise

        snapshot = MatchSnapshot.from_game_state(state, source=DataSource.GSI)
        self._store.apply(snapshot)

        with self._lock:
            self._last_payload_at = datetime.now(UTC)
            self._payload_count += 1
            was_connected = self._connected
            self._connected = True

        if not was_connected:
            self._bus.publish(GSIConnectionChanged(connected=True, detail="GSI feed active"))
            _log.info("GSI feed connected (map=%s)", state.map_name)

        self._bus.publish(GSIStateUpdated(game_state=state))
        _log.debug(
            "GSI update #%d map=%s round=%s score=%s-%s observed=%s",
            self._payload_count,
            state.map_name,
            state.round_number,
            state.ct_score,
            state.t_score,
            state.observed_player_name,
        )
        return state

    def mark_disconnected(self, detail: str = "GSI feed idle") -> None:
        """Flag the feed as disconnected and emit an event (idempotent)."""
        with self._lock:
            if not self._connected:
                return
            self._connected = False
        self._bus.publish(GSIConnectionChanged(connected=False, detail=detail))
        _log.info("GSI feed disconnected: %s", detail)

    def is_stale(self, stale_after_seconds: float, now: datetime | None = None) -> bool:
        """Whether the feed has been silent longer than the threshold."""
        with self._lock:
            last = self._last_payload_at
            connected = self._connected
        if not connected or last is None:
            return False
        now = now or datetime.now(UTC)
        return (now - last).total_seconds() > stale_after_seconds

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _authenticate(self, payload: dict) -> None:
        if not self._require_auth or not self._auth_token:
            return
        token = None
        auth = payload.get("auth")
        if isinstance(auth, dict):
            token = auth.get("token")
        if token != self._auth_token:
            _log.warning("Rejected GSI payload with invalid auth token")
            raise GSIAuthError("Invalid or missing GSI auth token")
