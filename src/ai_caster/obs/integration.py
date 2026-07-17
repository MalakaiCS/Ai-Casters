"""Replay-aware OBS scene switching.

Subscribes to replay state and, when auto-switching is enabled, moves OBS to the
replay scene while a replay is active and back to the live scene when it ends.
This is the foundation for the wider OBS surface (graphics triggers, additional
scene changes) in later work.
"""

from __future__ import annotations

from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger
from ai_caster.obs.controller import OBSController
from ai_caster.replay.events import ReplayStateChanged

_log = get_logger("obs.integration")


class OBSIntegration:
    """Wires replay transitions to OBS scene changes."""

    def __init__(
        self,
        event_bus: EventBus,
        controller: OBSController,
        *,
        auto_switch_scenes: bool = False,
        live_scene: str = "Live",
        replay_scene: str = "Replay",
    ) -> None:
        self._bus = event_bus
        self._controller = controller
        self._auto_switch = auto_switch_scenes
        self._live_scene = live_scene
        self._replay_scene = replay_scene
        self._unsubscribe = event_bus.subscribe(ReplayStateChanged, self._on_replay)

    @property
    def controller(self) -> OBSController:
        return self._controller

    @property
    def is_connected(self) -> bool:
        return self._controller.is_connected

    @property
    def auto_switch(self) -> bool:
        return self._auto_switch

    def current_scene(self) -> str | None:
        return self._controller.get_current_scene()

    def scenes(self) -> list[str]:
        return self._controller.list_scenes()

    def set_scenes(self, live_scene: str, replay_scene: str) -> None:
        self._live_scene = live_scene
        self._replay_scene = replay_scene

    def set_auto_switch(self, enabled: bool) -> None:
        self._auto_switch = enabled

    def reconfigure(
        self,
        controller: OBSController,
        *,
        auto_switch_scenes: bool | None = None,
        live_scene: str | None = None,
        replay_scene: str | None = None,
    ) -> None:
        """Swap in a freshly-built controller (e.g. after the operator edits the
        host/port/password) and apply any scene/auto-switch changes. The old
        controller is disconnected first."""
        try:
            self._controller.disconnect()
        except Exception:  # noqa: BLE001 - best effort
            _log.debug("Old OBS controller disconnect failed", exc_info=True)
        self._controller = controller
        if auto_switch_scenes is not None:
            self._auto_switch = auto_switch_scenes
        if live_scene is not None:
            self._live_scene = live_scene
        if replay_scene is not None:
            self._replay_scene = replay_scene

    def _on_replay(self, event: ReplayStateChanged) -> None:
        if not self._auto_switch or not self._controller.is_connected:
            return
        active = bool(getattr(event.state, "active", False))
        target = self._replay_scene if active else self._live_scene
        try:
            self._controller.set_scene(target)
        except Exception:  # noqa: BLE001 - OBS errors shouldn't disrupt the broadcast
            _log.exception("Failed to switch OBS scene to %s", target)

    def connect(self) -> None:
        try:
            self._controller.connect()
        except Exception:  # noqa: BLE001 - degrade gracefully if OBS is unreachable
            _log.warning("Could not connect to OBS; scene switching disabled.")

    def disconnect(self) -> None:
        self._controller.disconnect()

    def dispose(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self.disconnect()
