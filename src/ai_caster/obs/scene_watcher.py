"""Recognise a replay from OBS's current scene.

Many productions let a HUD manager (Lexogrine, etc.) switch OBS to a dedicated
replay scene. When that happens the app must *recognise* it — not drive it — so
the casters never describe replay footage as live. This watcher polls OBS's
current program scene and, when it matches the configured replay scene, publishes
the same :class:`ReplayStateChanged` the external replay system would, so the
Director and voices react through their existing path with no special casing.

The decision (:meth:`evaluate`) is pure and unit-tested with no threads; the loop
just polls on an interval and publishes whatever ``evaluate`` returns.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from ai_caster.core.logging import get_logger
from ai_caster.replay.events import ReplayStateChanged
from ai_caster.replay.models import ReplayState, ReplayType

_log = get_logger("obs.scene_watcher")


class OBSSceneWatcher:
    """Publishes replay state derived from OBS's current scene."""

    def __init__(
        self,
        event_bus,  # noqa: ANN001 - EventBus
        scene_provider: Callable[[], str | None],
        *,
        replay_scene: str = "Replay",
        enabled: bool = False,
        poll_seconds: float = 0.5,
    ) -> None:
        self._bus = event_bus
        self._scene_provider = scene_provider
        self._replay_scene = replay_scene
        self._enabled = enabled
        self._poll = poll_seconds

        self._lock = threading.RLock()
        self._last_active = False
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -- configuration (live) ------------------------------------------- #
    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled

    def set_replay_scene(self, scene: str) -> None:
        with self._lock:
            self._replay_scene = scene

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._last_active

    # -- decision (pure; fully testable) -------------------------------- #
    def evaluate(self, scene: str | None) -> ReplayStateChanged | None:
        """Return a transition event if the replay state changed, else None."""
        with self._lock:
            active = bool(self._enabled and scene and scene == self._replay_scene)
            if active == self._last_active:
                return None
            self._last_active = active
        transition = "started" if active else "ended"
        return ReplayStateChanged(
            state=ReplayState(active=active, replay_type=ReplayType.GENERIC),
            transition=transition,
        )

    def poll_once(self) -> None:
        """Read the current scene and publish a transition if one occurred."""
        try:
            scene = self._scene_provider()
        except Exception:  # noqa: BLE001 - an OBS hiccup must not crash the watcher
            _log.exception("Failed to read OBS scene")
            return
        event = self.evaluate(scene)
        if event is not None:
            _log.info("OBS scene replay %s (scene=%s)", event.transition, scene)
            self._bus.publish(event)

    # -- lifecycle ------------------------------------------------------ #
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="obs-scene-watcher", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._running and not self._stop.wait(self._poll):
            self.poll_once()

    def dispose(self) -> None:
        self._running = False
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
