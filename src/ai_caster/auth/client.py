"""The authentication client (Module 3).

Owns the current :class:`AuthSession`, orchestrates login/logout/refresh through
an injected :class:`AuthBackend`, optionally persists the session for "remember
me", and announces sign-in state on the event bus. Thread-safe: services on
other threads may read :attr:`account` while the UI drives login.
"""

from __future__ import annotations

import threading

from ai_caster.auth.backend import AuthBackend
from ai_caster.auth.events import AuthStateChanged
from ai_caster.auth.models import Account, AuthSession
from ai_caster.auth.store import SessionStore
from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger

_log = get_logger("auth.client")


class AuthClient:
    """Coordinates sign-in and exposes the current account/session."""

    def __init__(
        self,
        event_bus: EventBus,
        backend: AuthBackend,
        *,
        device_id: str,
        store: SessionStore | None = None,
        remember: bool = True,
    ) -> None:
        self._bus = event_bus
        self._backend = backend
        self._device_id = device_id
        self._store = store
        self._remember = remember
        self._lock = threading.RLock()
        self._session: AuthSession | None = None

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #
    @property
    def session(self) -> AuthSession | None:
        with self._lock:
            return self._session

    @property
    def account(self) -> Account | None:
        with self._lock:
            return self._session.account if self._session else None

    @property
    def is_authenticated(self) -> bool:
        with self._lock:
            return self._session is not None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def restore(self) -> bool:
        """Restore a persisted session (refreshing it if expired). Returns True if
        a usable session was restored."""
        if self._store is None:
            return False
        saved = self._store.load()
        if saved is None:
            return False
        if saved.is_expired():
            result = self._backend.refresh(saved, device_id=self._device_id)
            if not result.ok or result.session is None:
                _log.info("Saved session expired and could not be refreshed.")
                self._store.clear()
                return False
            saved = result.session
        self._set_session(saved, detail="restored")
        return True

    def login(self, email: str, password: str) -> bool:
        """Attempt sign-in. Returns True on success and announces the new state."""
        result = self._backend.login(email, password, device_id=self._device_id)
        if not result.ok or result.session is None:
            _log.info("Login rejected: %s", result.error)
            self._bus.publish(AuthStateChanged(authenticated=False, detail=result.error))
            return False
        self._set_session(result.session, detail="signed in")
        return True

    def refresh(self) -> bool:
        """Refresh the current session's tokens. Returns True on success."""
        with self._lock:
            current = self._session
        if current is None:
            return False
        result = self._backend.refresh(current, device_id=self._device_id)
        if not result.ok or result.session is None:
            return False
        self._set_session(result.session, detail="refreshed")
        return True

    def logout(self) -> None:
        with self._lock:
            current = self._session
            self._session = None
        if current is not None:
            try:
                self._backend.logout(current)
            except Exception:  # noqa: BLE001 - logout is best-effort
                _log.exception("Backend logout failed")
        if self._store is not None:
            self._store.clear()
        self._bus.publish(AuthStateChanged(authenticated=False, detail="signed out"))

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _set_session(self, session: AuthSession, *, detail: str) -> None:
        with self._lock:
            self._session = session
        if self._store is not None and self._remember:
            try:
                self._store.save(session)
            except OSError:
                _log.exception("Could not persist session")
        self._bus.publish(
            AuthStateChanged(authenticated=True, account=session.account, detail=detail)
        )
