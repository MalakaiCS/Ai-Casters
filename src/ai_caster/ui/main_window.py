"""The main application window and desktop entry point.

Builds a sidebar-navigation shell (a list + a stacked widget) that hosts a live
view for every module — dashboard, GSI, match, statistics, capture, vision,
director, commentary, voice/OBS, replay, account, diagnostics and settings. Wires
the core :class:`~ai_caster.app.Application` to the UI through the
:class:`~ai_caster.ui.qt_event_bridge.QtEventBridge`.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ai_caster import __brand__, __version__
from ai_caster.app import Application
from ai_caster.core.logging import get_logger
from ai_caster.ui.branding import app_icon, logo_pixmap
from ai_caster.ui.qt_event_bridge import QtEventBridge
from ai_caster.ui.views.account_view import AccountView
from ai_caster.ui.views.capture_view import CaptureView
from ai_caster.ui.views.commentary_view import CommentaryView
from ai_caster.ui.views.dashboard import DashboardView
from ai_caster.ui.views.diagnostics_view import DiagnosticsView
from ai_caster.ui.views.director_view import DirectorView
from ai_caster.ui.views.gsi_view import GSIView
from ai_caster.ui.views.match_view import MatchView
from ai_caster.ui.views.replay_view import ReplayView
from ai_caster.ui.views.settings_view import SettingsView
from ai_caster.ui.views.statistics_view import StatisticsView
from ai_caster.ui.views.team_view import TeamView
from ai_caster.ui.views.training_view import TrainingView
from ai_caster.ui.views.vision_view import VisionView
from ai_caster.ui.views.voice_view import VoiceView

_log = get_logger("ui.main")


class MainWindow(QMainWindow):
    """Top-level window hosting navigation and views."""

    def __init__(self, application: Application) -> None:
        super().__init__()
        self._app = application
        self.setWindowTitle(f"{__brand__} · v{__version__}")
        self.setWindowIcon(app_icon())
        self.resize(1024, 700)

        self._bridge = QtEventBridge(application.event_bus, self)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left column: brand logo above the navigation list.
        sidebar = QWidget()
        sidebar.setFixedWidth(190)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        brand_pixmap = logo_pixmap(150)
        if not brand_pixmap.isNull():
            brand = QLabel()
            brand.setPixmap(brand_pixmap)
            brand.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            brand.setStyleSheet("padding: 10px 0;")
            sidebar_layout.addWidget(brand)

        self._nav = QListWidget()
        self._nav.setStyleSheet("QListWidget { font-size: 14px; padding: 6px; }")
        self._stack = QStackedWidget()
        sidebar_layout.addWidget(self._nav, stretch=1)

        layout.addWidget(sidebar)
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

        self._dashboard = DashboardView(application.gsi_server.address, application.broadcast)
        self._gsi_view = GSIView(application.gsi_server.address)
        self._match_view = MatchView()
        self._statistics_view = StatisticsView(application.statistics)
        self._capture_view = CaptureView(application.capture)
        self._vision_view = VisionView(application.vision)
        self._director_view = DirectorView(application.director)
        self._commentary_view = CommentaryView(application.play_by_play, application.analyst)
        self._voice_view = VoiceView(
            application.voice, application.obs, application.settings_manager
        )
        self._replay_view = ReplayView(
            application.replay_receiver, application.replay_server.address
        )
        self._account_view = AccountView(
            application.auth, application.licensing, application.updater
        )
        self._team_view = TeamView(application.auth, application.team)
        self._training_view = TrainingView(
            application.auth, application.settings_manager, application.style_hub
        )
        self._diagnostics_view = DiagnosticsView(
            application.paths.log_dir if application.settings.logging.log_to_file else None,
            log_tail_lines=application.settings.diagnostics.log_tail_lines,
        )
        self._settings_view = SettingsView(application.settings_manager)

        # Live views (Milestones 1–6).
        self._add_view("Dashboard", self._dashboard)
        self._add_view("Live GSI", self._gsi_view)
        self._add_view("Match Engine", self._match_view)
        self._add_view("Statistics", self._statistics_view)
        self._add_view("Video Capture", self._capture_view)
        self._add_view("Computer Vision", self._vision_view)
        self._add_view("Commentary Director", self._director_view)
        self._add_view("Commentary AIs", self._commentary_view)
        self._add_view("Voice, Audio & OBS", self._voice_view)
        self._add_view("Replay", self._replay_view)
        self._add_view("Account & License", self._account_view)
        self._add_view("Team & Roles", self._team_view)
        self._add_view("Train the AI", self._training_view)
        self._add_view("Diagnostics", self._diagnostics_view)
        self._add_view("Settings", self._settings_view)

        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

        # Wire core events -> UI (marshalled onto the Qt thread by the bridge).
        self._bridge.gsi_state_updated.connect(self._gsi_view.on_gsi_state)
        self._bridge.gsi_connection_changed.connect(self._gsi_view.on_connection_changed)
        self._bridge.gsi_connection_changed.connect(self._dashboard.set_feed_connected)
        self._bridge.settings_changed.connect(lambda _s: self._settings_view.reload())
        self._bridge.match_updated.connect(self._match_view.on_match_updated)
        self._bridge.match_updated.connect(lambda _m: self._statistics_view.refresh())
        self._bridge.match_event.connect(self._match_view.on_match_event)
        self._bridge.capture_status.connect(self._capture_view.on_capture_status)
        self._bridge.capture_stats.connect(self._capture_view.on_capture_stats)
        self._bridge.vision_state.connect(self._vision_view.on_vision_state)
        self._bridge.directive_issued.connect(self._director_view.on_directive)
        self._bridge.replay_state.connect(self._director_view.on_replay_state)
        self._bridge.replay_state.connect(self._replay_view.on_replay_state)
        self._bridge.commentary_line.connect(self._commentary_view.on_commentary_line)
        self._bridge.commentary_line.connect(self._voice_view.on_commentary_line)
        self._bridge.replay_state.connect(self._voice_view.on_replay_state)
        self._bridge.auth_state.connect(self._account_view.on_auth_state)
        self._bridge.auth_state.connect(self._team_view.on_auth_state)
        self._bridge.auth_state.connect(self._training_view.on_auth_state)
        self._bridge.license_state.connect(self._account_view.on_license_state)
        self._bridge.update_available.connect(self._account_view.on_update_available)
        self._bridge.diagnostics.connect(self._diagnostics_view.on_diagnostics)
        self._bridge.broadcast_state.connect(self._dashboard.on_broadcast_state)

        self.statusBar().showMessage(f"GSI endpoint: {application.gsi_server.address}")

    def _add_view(self, name: str, widget: QWidget) -> None:
        QListWidgetItem(name, self._nav)
        self._stack.addWidget(widget)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._dashboard.set_gsi_running(self._app.gsi_server.is_running)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        _log.info("Main window closing; stopping services")
        self._bridge.dispose()
        self._app.stop_services()
        super().closeEvent(event)


def run_desktop_app(argv: list[str] | None = None) -> int:
    """Construct the core application, start services and run the Qt loop."""
    application = Application()

    qt_app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    qt_app.setApplicationName(__brand__)
    qt_app.setWindowIcon(app_icon())

    try:
        application.start_services()
    except OSError as exc:
        # Most commonly a port already in use.
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            "Startup error",
            f"Could not start the GSI server on {application.gsi_server.address}:\n{exc}\n\n"
            "Change the port in Settings and restart.",
        )

    # Accounts are required: gate on sign-in (a restored session skips this).
    from ai_caster.ui.auth_window import require_sign_in

    if not require_sign_in(application.auth):
        _log.info("Sign-in dismissed; exiting.")
        application.stop_services()
        return 0

    window = MainWindow(application)
    window.show()
    return qt_app.exec()
