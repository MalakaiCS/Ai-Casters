"""Bridges the thread-safe :class:`EventBus` onto the Qt event loop.

The GSI server publishes events from a network thread. Qt widgets may only be
touched from the Qt thread. This bridge subscribes to the bus and re-emits each
event as a Qt signal; because the bridge lives on the Qt thread, Qt's queued
connections automatically marshal the payload across the thread boundary. Views
connect to these signals instead of subscribing to the bus directly.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ai_caster.core.events import (
    Event,
    GSIConnectionChanged,
    GSIStateUpdated,
    SettingsChanged,
)


class QtEventBridge(QObject):
    """Re-emits :class:`EventBus` events as Qt signals on the Qt thread."""

    gsi_state_updated = Signal(object)  # -> GameState
    gsi_connection_changed = Signal(bool, str)
    settings_changed = Signal(str)

    def __init__(self, event_bus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bus = event_bus
        self._unsubscribes = [
            event_bus.subscribe(GSIStateUpdated, self._on_gsi_state),
            event_bus.subscribe(GSIConnectionChanged, self._on_connection),
            event_bus.subscribe(SettingsChanged, self._on_settings),
        ]

    # These run on the publisher's (network) thread; emitting a Qt signal with a
    # queued connection safely hands off to the Qt thread.
    def _on_gsi_state(self, event: GSIStateUpdated) -> None:
        self.gsi_state_updated.emit(event.game_state)

    def _on_connection(self, event: GSIConnectionChanged) -> None:
        self.gsi_connection_changed.emit(event.connected, event.detail)

    def _on_settings(self, event: SettingsChanged) -> None:
        self.settings_changed.emit(event.section)

    def dispose(self) -> None:
        """Unsubscribe from the bus (call on shutdown)."""
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes.clear()

    # Silence unused-import lint for Event (kept for typing/readability).
    _ = Event
