"""The broadcast controller — the single 'go live' switch (M9).

The individual subsystems (capture, vision, voice) already start and stop
independently, but an operator — and the global hotkeys — need *one* action that
turns the whole cast on or off, mutes everything, or forces replay mode. This
controller is that seam. It owns no threads of its own; it composes the
subsystems it is given and announces state on the bus, so both the UI and the
hotkey manager drive the exact same code path.

Casting is gated on the ``LIVE_CASTING`` entitlement, so licensing is enforced at
the one place it matters rather than sprinkled through the pipeline.
"""

from __future__ import annotations

import threading

from ai_caster.broadcast.events import BroadcastStateChanged
from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger
from ai_caster.licensing.client import LicensingClient
from ai_caster.licensing.models import Feature
from ai_caster.replay.events import ReplayStateChanged
from ai_caster.replay.models import ReplayState, ReplayType

_log = get_logger("broadcast.controller")


class BroadcastController:
    """Starts/stops the whole cast, master-mutes, and forces replay mode."""

    def __init__(
        self,
        event_bus: EventBus,
        *,
        capture,
        vision,
        voice,
        licensing: LicensingClient | None = None,
        enable_vision_on_cast: bool = True,
    ) -> None:
        self._bus = event_bus
        self._capture = capture
        self._vision = vision
        self._voice = voice
        self._licensing = licensing
        self._enable_vision = enable_vision_on_cast
        self._lock = threading.RLock()
        self._casting = False
        self._muted = False
        self._forced_replay = False

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #
    @property
    def is_casting(self) -> bool:
        with self._lock:
            return self._casting

    @property
    def is_muted(self) -> bool:
        with self._lock:
            return self._muted

    @property
    def forced_replay(self) -> bool:
        with self._lock:
            return self._forced_replay

    # ------------------------------------------------------------------ #
    # Casting
    # ------------------------------------------------------------------ #
    def start_casting(self) -> bool:
        """Bring the cast live (capture + vision). Returns True if now casting."""
        with self._lock:
            if self._casting:
                return True
            if self._licensing is not None and not self._licensing.is_entitled(
                Feature.LIVE_CASTING
            ):
                _log.warning("Casting blocked: the current plan does not include live casting.")
                self._bus.publish(
                    BroadcastStateChanged(casting=False, muted=self._muted, detail="not entitled")
                )
                return False
            try:
                if not self._capture.is_running:
                    self._capture.start()
                if self._enable_vision:
                    self._vision.set_enabled(True)
            except Exception:  # noqa: BLE001 - surface failure without crashing
                _log.exception("Could not start casting")
                self._bus.publish(
                    BroadcastStateChanged(casting=False, muted=self._muted, detail="start failed")
                )
                return False
            self._casting = True
        self._bus.publish(BroadcastStateChanged(casting=True, muted=self._muted, detail="casting"))
        _log.info("Casting started")
        return True

    def stop_casting(self) -> None:
        """Take the cast off-air (stop capture, disable vision)."""
        with self._lock:
            if not self._casting:
                return
            try:
                self._vision.set_enabled(False)
                if self._capture.is_running:
                    self._capture.stop()
            except Exception:  # noqa: BLE001 - always reach a stopped state
                _log.exception("Error while stopping casting")
            self._casting = False
        self._bus.publish(BroadcastStateChanged(casting=False, muted=self._muted, detail="stopped"))
        _log.info("Casting stopped")

    def toggle_casting(self) -> bool:
        """Toggle casting; returns the new casting state."""
        if self.is_casting:
            self.stop_casting()
            return False
        return self.start_casting()

    # ------------------------------------------------------------------ #
    # Master mute
    # ------------------------------------------------------------------ #
    def set_muted(self, muted: bool) -> None:
        with self._lock:
            self._muted = muted
            casting = self._casting
        self._voice.set_muted(muted)
        self._bus.publish(
            BroadcastStateChanged(
                casting=casting, muted=muted, detail="muted" if muted else "unmuted"
            )
        )

    def toggle_mute(self) -> bool:
        """Toggle master mute; returns the new muted state."""
        new_state = not self.is_muted
        self.set_muted(new_state)
        return new_state

    # ------------------------------------------------------------------ #
    # Forced replay mode
    # ------------------------------------------------------------------ #
    def set_forced_replay(self, active: bool) -> None:
        """Manually force (or release) replay mode.

        Publishes an authoritative :class:`ReplayStateChanged` so the Director's
        existing "never live during replay" enforcement applies — reusing the real
        machinery rather than a parallel override path.
        """
        with self._lock:
            self._forced_replay = active
        state = ReplayState(active=active, replay_type=ReplayType.HIGHLIGHT)
        transition = "started" if active else "ended"
        self._bus.publish(ReplayStateChanged(state=state, transition=transition))
        _log.info("Forced replay mode %s", "on" if active else "off")

    def toggle_forced_replay(self) -> bool:
        """Toggle forced replay mode; returns the new state."""
        new_state = not self.forced_replay
        self.set_forced_replay(new_state)
        return new_state

    # ------------------------------------------------------------------ #
    def dispose(self) -> None:
        """Ensure the cast is stopped (called on shutdown)."""
        self.stop_casting()
