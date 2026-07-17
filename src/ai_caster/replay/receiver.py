"""Framework-agnostic replay-event receiver.

Ingests replay events from the external replay system and maintains the
authoritative :class:`ReplayState`. Like the GSI receiver, the domain logic is
separate from any transport so it is fully unit-testable.

Accepted payloads (JSON objects)::

    {"event": "started", "type": "kill", "speed": 0.5}
    {"event": "speed",   "speed": 1.0}
    {"event": "ended"}
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger
from ai_caster.replay.events import ReplayStateChanged
from ai_caster.replay.models import ReplayState, ReplayType

_log = get_logger("replay.receiver")


class ReplayEventError(ValueError):
    """Raised for a malformed or unknown replay event."""


class ReplayReceiver:
    """Maintains replay state from external events and publishes changes."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._bus = event_bus
        self._lock = threading.RLock()
        self._state = ReplayState()

    @property
    def state(self) -> ReplayState:
        with self._lock:
            return self._state

    @property
    def is_replay_active(self) -> bool:
        with self._lock:
            return self._state.active

    def handle_event(self, payload: dict) -> ReplayState:
        """Apply one replay event and return the new state.

        Raises :class:`ReplayEventError` for unknown/malformed events.
        """
        event = payload.get("event")
        if event == "started":
            state = self._on_started(payload)
            transition = "started"
        elif event == "ended":
            state = ReplayState(active=False)
            transition = "ended"
        elif event == "speed":
            state = self._on_speed(payload)
            transition = "speed"
        else:
            raise ReplayEventError(f"Unknown replay event: {event!r}")

        with self._lock:
            self._state = state
        if self._bus is not None:
            self._bus.publish(ReplayStateChanged(state=state, transition=transition))
        _log.info(
            "Replay %s (active=%s, type=%s, speed=%.2f)",
            transition,
            state.active,
            state.replay_type,
            state.speed,
        )
        return state

    def reset(self) -> None:
        with self._lock:
            self._state = ReplayState()

    # ------------------------------------------------------------------ #
    def _on_started(self, payload: dict) -> ReplayState:
        raw_type = payload.get("type", "generic")
        try:
            replay_type = ReplayType(raw_type)
        except ValueError:
            replay_type = ReplayType.GENERIC
        speed = self._coerce_speed(payload.get("speed", 1.0))
        return ReplayState(
            active=True,
            replay_type=replay_type,
            speed=speed,
            started_at=datetime.now(UTC),
        )

    def _on_speed(self, payload: dict) -> ReplayState:
        with self._lock:
            current = self._state
        speed = self._coerce_speed(payload.get("speed", current.speed))
        return ReplayState(
            active=current.active,
            replay_type=current.replay_type,
            speed=speed,
            started_at=current.started_at,
        )

    @staticmethod
    def _coerce_speed(value: object) -> float:
        try:
            speed = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ReplayEventError(f"Invalid replay speed: {value!r}") from exc
        if speed <= 0:
            raise ReplayEventError(f"Replay speed must be positive, got {speed}")
        return speed
