"""Module 8 — the Match State Engine: the single source of truth.

Subscribes to the GSI stream and, on every payload:

1. **Detects** match events by diffing against the previous payload.
2. **Rebuilds** the complete :class:`LiveMatch` model (scores, economy, players,
   momentum, importance) carrying round *history* forward.
3. **Accumulates** statistics from the authoritative snapshot and the events.
4. **Persists** rounds, events and stats (when a repository is configured).
5. **Publishes** a :class:`MatchModelUpdated` plus each detected event on the bus.

Priority of truth (**Server > GSI > Vision > Inference**) is honoured: today the
engine consumes confirmed GSI only, and the model/store already carry a source
tag so Vision (M4) can be fused in later without uncertain data ever overwriting
confirmed facts.

Thread-safety: :meth:`on_gsi_update` runs on the GSI network thread. All shared
state is guarded by a lock and only *immutable* snapshots (``LiveMatch``) are
handed to readers, so the UI never sees a half-updated model.
"""

from __future__ import annotations

import threading

from ai_caster.core.events import EventBus, GSIStateUpdated
from ai_caster.core.logging import get_logger
from ai_caster.detection.detectors import EventDetector
from ai_caster.detection.events import (
    MatchEnded,
    MatchEvent,
    RoundEnded,
)
from ai_caster.gsi.models import GameState
from ai_caster.match.events import MatchModelUpdated
from ai_caster.match.model import (
    DEFAULT_ROUNDS_TO_WIN,
    LiveMatch,
    RoundEndReason,
    RoundRecord,
    Side,
    build_live_match,
)
from ai_caster.persistence.repository import MatchRepository
from ai_caster.statistics.engine import StatisticsEngine
from ai_caster.vision.events import VisionStateUpdated

_log = get_logger("match.engine")


class MatchStateEngine:
    """Fuses the GSI stream into the live match model, events and statistics."""

    def __init__(
        self,
        event_bus: EventBus,
        statistics: StatisticsEngine,
        *,
        detector: EventDetector | None = None,
        repository: MatchRepository | None = None,
        rounds_to_win: int = DEFAULT_ROUNDS_TO_WIN,
        persist: bool = True,
    ) -> None:
        self._bus = event_bus
        self._stats = statistics
        self._detector = detector or EventDetector()
        self._repo = repository
        self._rounds_to_win = rounds_to_win
        self._persist = persist and repository is not None

        self._lock = threading.RLock()
        self._history: list[RoundRecord] = []
        self._live: LiveMatch | None = None
        self._current_map: str | None = None
        self._match_id: int | None = None
        self._vision_state = None  # latest VisionState annotation (GSI stays authoritative)
        self._unsubscribes = [
            event_bus.subscribe(GSIStateUpdated, self._on_gsi_event),
            event_bus.subscribe(VisionStateUpdated, self._on_vision_event),
        ]

    # ------------------------------------------------------------------ #
    # Accessors
    # ------------------------------------------------------------------ #
    @property
    def live_match(self) -> LiveMatch | None:
        with self._lock:
            return self._live

    @property
    def statistics(self) -> StatisticsEngine:
        return self._stats

    @property
    def match_id(self) -> int | None:
        return self._match_id

    def dispose(self) -> None:
        for unsubscribe in self._unsubscribes:
            unsubscribe()

    # ------------------------------------------------------------------ #
    # Core
    # ------------------------------------------------------------------ #
    def _on_gsi_event(self, event: GSIStateUpdated) -> None:
        if event.game_state is not None:
            self.on_gsi_update(event.game_state)

    def _on_vision_event(self, event: VisionStateUpdated) -> None:
        # Store the latest vision annotation; it is attached to the model on the
        # next GSI update. Vision never overrides GSI-confirmed fields.
        with self._lock:
            self._vision_state = event.state

    def on_gsi_update(self, state: GameState) -> list[MatchEvent]:
        """Process one GSI payload. Returns the events detected (for tests)."""
        with self._lock:
            self._handle_map_change(state)
            events = self._detector.detect(state)
            vision = self._vision_state

            # Build the model from the current payload with existing history.
            live = build_live_match(
                state,
                history=tuple(self._history),
                rounds_to_win=self._rounds_to_win,
                vision=vision,
            )

            # Authoritative + event-derived statistics.
            self._stats.sync_from_match(live)
            for detected in events:
                self._stats.record_event(detected)

            self._ensure_match(state)

            # Finalise a round when one ended (round stats still reflect it now).
            for detected in events:
                if isinstance(detected, RoundEnded):
                    self._finalise_round(detected, live)
                elif isinstance(detected, MatchEnded):
                    self._finalise_match(detected)

            # Rebuild if history changed so momentum/importance reflect it now.
            if any(isinstance(e, RoundEnded) for e in events):
                live = build_live_match(
                    state,
                    history=tuple(self._history),
                    rounds_to_win=self._rounds_to_win,
                    vision=vision,
                )

            self._live = live

            # Persist events.
            if self._persist and self._match_id is not None:
                for detected in events:
                    self._repo.record_event(self._match_id, detected)

        # Publish outside the lock so subscribers can't deadlock the engine.
        self._bus.publish(MatchModelUpdated(match=live))
        for detected in events:
            self._bus.publish(detected)
        return events

    # ------------------------------------------------------------------ #
    # Round / match lifecycle
    # ------------------------------------------------------------------ #
    def _finalise_round(self, event: RoundEnded, live: LiveMatch) -> None:
        self._stats.record_round_end(live)
        winner = Side(event.winner) if event.winner in ("CT", "T") else None
        record = RoundRecord(
            number=event.round_number,
            winner=winner,
            reason=RoundEndReason(event.reason)
            if event.reason in RoundEndReason._value2member_map_
            else RoundEndReason.UNKNOWN,
            bomb_planted=event.bomb_planted,
            ct_buy=live.ct.buy_type,
            t_buy=live.t.buy_type,
        )
        self._history.append(record)
        if self._persist and self._match_id is not None:
            self._repo.record_round(self._match_id, record)
            self._repo.save_statistics(self._match_id, self._stats.statistics)

    def _finalise_match(self, event: MatchEnded) -> None:
        if self._persist and self._match_id is not None:
            self._repo.finish_match(self._match_id, event.ct_score, event.t_score)
            self._repo.save_statistics(self._match_id, self._stats.statistics)
        _log.info("Match ended: %s won (%d-%d)", event.winner, event.ct_score, event.t_score)

    def _handle_map_change(self, state: GameState) -> None:
        map_name = state.map_name
        if map_name and map_name != self._current_map:
            if self._current_map is not None:
                _log.info(
                    "New map detected (%s -> %s); resetting match state",
                    self._current_map,
                    map_name,
                )
            self._current_map = map_name
            self._history.clear()
            self._stats.reset()
            self._detector.reset()
            self._match_id = None

    def _ensure_match(self, state: GameState) -> None:
        if not self._persist or self._match_id is not None:
            return
        if not state.map_name:
            return
        ct_name = state.map.team_ct.name if state.map and state.map.team_ct else ""
        t_name = state.map.team_t.name if state.map and state.map.team_t else ""
        self._match_id = self._repo.start_match(state.map_name, ct_name or "", t_name or "")
        _log.info("Started match record #%s on %s", self._match_id, state.map_name)
