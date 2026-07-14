"""Bridges the thread-safe :class:`EventBus` onto the Qt event loop.

The GSI server publishes events from a network thread. Qt widgets may only be
touched from the Qt thread. This bridge subscribes to the bus and re-emits each
event as a Qt signal; because the bridge lives on the Qt thread, Qt's queued
connections automatically marshal the payload across the thread boundary. Views
connect to these signals instead of subscribing to the bus directly.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ai_caster.auth.events import AuthStateChanged
from ai_caster.capture.events import CaptureStatsUpdated, CaptureStatusChanged
from ai_caster.commentary.lines import CommentaryLineGenerated
from ai_caster.core.events import (
    Event,
    GSIConnectionChanged,
    GSIStateUpdated,
    SettingsChanged,
)
from ai_caster.detection.events import MatchEvent
from ai_caster.director.directives import CommentaryDirectiveIssued
from ai_caster.licensing.events import LicenseStateChanged
from ai_caster.match.events import MatchModelUpdated
from ai_caster.replay.events import ReplayStateChanged
from ai_caster.updater.events import UpdateAvailable
from ai_caster.vision.events import VisionStateUpdated


class QtEventBridge(QObject):
    """Re-emits :class:`EventBus` events as Qt signals on the Qt thread."""

    gsi_state_updated = Signal(object)  # -> GameState
    gsi_connection_changed = Signal(bool, str)
    settings_changed = Signal(str)
    match_updated = Signal(object)  # -> LiveMatch
    match_event = Signal(object)  # -> MatchEvent
    capture_status = Signal(bool, str, str)  # running, source, detail
    capture_stats = Signal(object)  # -> CaptureStats
    vision_state = Signal(object)  # -> VisionState
    directive_issued = Signal(object)  # -> CommentaryDirective
    replay_state = Signal(object, str)  # ReplayState, transition
    commentary_line = Signal(object)  # -> CommentaryLine
    auth_state = Signal(bool, object, str)  # authenticated, account, detail
    license_state = Signal(str, str, bool)  # status, tier, offline
    update_available = Signal(object, str, str, bool)  # info, current, latest, mandatory

    def __init__(self, event_bus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bus = event_bus
        self._unsubscribes = [
            event_bus.subscribe(GSIStateUpdated, self._on_gsi_state),
            event_bus.subscribe(GSIConnectionChanged, self._on_connection),
            event_bus.subscribe(SettingsChanged, self._on_settings),
            event_bus.subscribe(MatchModelUpdated, self._on_match_updated),
            event_bus.subscribe(MatchEvent, self._on_match_event),
            event_bus.subscribe(CaptureStatusChanged, self._on_capture_status),
            event_bus.subscribe(CaptureStatsUpdated, self._on_capture_stats),
            event_bus.subscribe(VisionStateUpdated, self._on_vision_state),
            event_bus.subscribe(CommentaryDirectiveIssued, self._on_directive),
            event_bus.subscribe(ReplayStateChanged, self._on_replay_state),
            event_bus.subscribe(CommentaryLineGenerated, self._on_commentary_line),
            event_bus.subscribe(AuthStateChanged, self._on_auth_state),
            event_bus.subscribe(LicenseStateChanged, self._on_license_state),
            event_bus.subscribe(UpdateAvailable, self._on_update_available),
        ]

    # These run on the publisher's (network) thread; emitting a Qt signal with a
    # queued connection safely hands off to the Qt thread.
    def _on_gsi_state(self, event: GSIStateUpdated) -> None:
        self.gsi_state_updated.emit(event.game_state)

    def _on_connection(self, event: GSIConnectionChanged) -> None:
        self.gsi_connection_changed.emit(event.connected, event.detail)

    def _on_settings(self, event: SettingsChanged) -> None:
        self.settings_changed.emit(event.section)

    def _on_match_updated(self, event: MatchModelUpdated) -> None:
        self.match_updated.emit(event.match)

    def _on_match_event(self, event: MatchEvent) -> None:
        self.match_event.emit(event)

    def _on_capture_status(self, event: CaptureStatusChanged) -> None:
        self.capture_status.emit(event.running, event.source, event.detail)

    def _on_capture_stats(self, event: CaptureStatsUpdated) -> None:
        self.capture_stats.emit(event.stats)

    def _on_vision_state(self, event: VisionStateUpdated) -> None:
        self.vision_state.emit(event.state)

    def _on_directive(self, event: CommentaryDirectiveIssued) -> None:
        self.directive_issued.emit(event.directive)

    def _on_replay_state(self, event: ReplayStateChanged) -> None:
        self.replay_state.emit(event.state, event.transition)

    def _on_commentary_line(self, event: CommentaryLineGenerated) -> None:
        self.commentary_line.emit(event.line)

    def _on_auth_state(self, event: AuthStateChanged) -> None:
        self.auth_state.emit(event.authenticated, event.account, event.detail)

    def _on_license_state(self, event: LicenseStateChanged) -> None:
        self.license_state.emit(event.status, event.tier, event.offline)

    def _on_update_available(self, event: UpdateAvailable) -> None:
        self.update_available.emit(
            event.update, event.current_version, event.latest_version, event.mandatory
        )

    def dispose(self) -> None:
        """Unsubscribe from the bus (call on shutdown)."""
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes.clear()

    # Silence unused-import lint for Event (kept for typing/readability).
    _ = Event
