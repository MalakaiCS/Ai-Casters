"""The main application window and desktop entry point.

Builds a sidebar-navigation shell (a list + a stacked widget) that hosts the
live views implemented in Milestone 1 and placeholders for every future module,
so the full product surface is visible from day one. Wires the core
:class:`~ai_caster.app.Application` to the UI through the
:class:`~ai_caster.ui.qt_event_bridge.QtEventBridge`.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from ai_caster import __app_name__, __version__
from ai_caster.app import Application
from ai_caster.core.logging import get_logger
from ai_caster.ui.qt_event_bridge import QtEventBridge
from ai_caster.ui.views.dashboard import DashboardView
from ai_caster.ui.views.gsi_view import GSIView
from ai_caster.ui.views.placeholder import PlaceholderView
from ai_caster.ui.views.settings_view import SettingsView

_log = get_logger("ui.main")


class MainWindow(QMainWindow):
    """Top-level window hosting navigation and views."""

    def __init__(self, application: Application) -> None:
        super().__init__()
        self._app = application
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.resize(1024, 700)

        self._bridge = QtEventBridge(application.event_bus, self)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._nav = QListWidget()
        self._nav.setFixedWidth(190)
        self._nav.setStyleSheet("QListWidget { font-size: 14px; padding: 6px; }")
        self._stack = QStackedWidget()

        layout.addWidget(self._nav)
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

        self._dashboard = DashboardView(application.gsi_server.address)
        self._gsi_view = GSIView(application.gsi_server.address)
        self._settings_view = SettingsView(application.settings_manager)

        # Live (Milestone 1) views.
        self._add_view("Dashboard", self._dashboard)
        self._add_view("Live GSI", self._gsi_view)
        self._add_view("Settings", self._settings_view)

        # Placeholders for future modules (navigable from day one).
        self._add_placeholders()

        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

        # Wire core events -> UI (marshalled onto the Qt thread by the bridge).
        self._bridge.gsi_state_updated.connect(self._gsi_view.on_gsi_state)
        self._bridge.gsi_connection_changed.connect(self._gsi_view.on_connection_changed)
        self._bridge.gsi_connection_changed.connect(self._dashboard.set_feed_connected)
        self._bridge.settings_changed.connect(lambda _s: self._settings_view.reload())

        self.statusBar().showMessage(f"GSI endpoint: {application.gsi_server.address}")

    def _add_view(self, name: str, widget: QWidget) -> None:
        QListWidgetItem(name, self._nav)
        self._stack.addWidget(widget)

    def _add_placeholders(self) -> None:
        future = [
            ("Match Engine", "Milestone 2", "Single source of truth fusing GSI, history, vision."),
            ("Statistics", "Milestone 2", "Round/economy/momentum tracking and match statistics."),
            ("Video Capture", "Milestone 3", "Capture the CS2 observer feed at 1080p60."),
            ("Computer Vision", "Milestone 4", "Kill feed, HUD, utility and camera understanding."),
            ("Commentary Director", "Milestone 5", "Decides who speaks, when, and broadcast flow."),
            ("Replay", "Milestone 5", "External replay events; never call replays live."),
            ("Play-by-Play AI", "Milestone 6", "High-energy original play-by-play commentary."),
            ("Analyst AI", "Milestone 6", "Longer analytical, strategic commentary."),
            ("Voice Engine", "Milestone 7", "Two independent voice channels + monitor mix."),
            ("Audio & OBS", "Milestone 7", "Windows device routing and OBS WebSocket."),
            ("Account & License", "Milestone 8", "Login, licensing, devices, cloud settings."),
            ("Diagnostics", "Milestone 9", "Latency, performance and log inspection."),
        ]
        for title, milestone, description in future:
            self._add_view(title, PlaceholderView(title, milestone, description))

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

    window = MainWindow(application)
    window.show()
    return qt_app.exec()
