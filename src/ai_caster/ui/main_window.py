"""The main application window and desktop entry point.

Builds a sidebar-navigation shell (a list + a stacked widget) that hosts a live
view for every module — dashboard, GSI, match, statistics, capture, vision,
director, commentary, voice/OBS, replay, account, diagnostics and settings. Wires
the core :class:`~ai_caster.app.Application` to the UI through the
:class:`~ai_caster.ui.qt_event_bridge.QtEventBridge`.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ai_caster import __brand__, __version__
from ai_caster.app import Application
from ai_caster.auth.roles import Role, can_manage_roles, can_train
from ai_caster.core.logging import get_logger
from ai_caster.ui.branding import app_icon, logo_pixmap
from ai_caster.ui.qt_event_bridge import QtEventBridge
from ai_caster.ui.theme import MUTED, apply_theme
from ai_caster.ui.views.account_view import AccountView
from ai_caster.ui.views.capture_view import CaptureView
from ai_caster.ui.views.commentary_view import CommentaryView
from ai_caster.ui.views.dashboard import DashboardView
from ai_caster.ui.views.diagnostics_view import DiagnosticsView
from ai_caster.ui.views.director_view import DirectorView
from ai_caster.ui.views.gsi_view import GSIView
from ai_caster.ui.views.match_view import MatchView
from ai_caster.ui.views.rehearsal_view import RehearsalView
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
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_account_bar())

        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left column: brand logo above the navigation list.
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        brand_pixmap = logo_pixmap(150)
        if not brand_pixmap.isNull():
            brand = QLabel()
            brand.setPixmap(brand_pixmap)
            brand.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            brand.setStyleSheet("padding: 14px 0 6px 0;")
            sidebar_layout.addWidget(brand)

        self._nav = QListWidget()
        self._nav.setObjectName("nav")
        self._stack = QStackedWidget()
        sidebar_layout.addWidget(self._nav, stretch=1)

        layout.addWidget(sidebar)
        layout.addWidget(self._stack, stretch=1)
        outer.addWidget(content, stretch=1)
        self.setCentralWidget(central)

        self._dashboard = DashboardView(
            application.gsi_server.address,
            application.broadcast,
            application.settings_manager,
        )
        self._gsi_view = GSIView(application.gsi_server.address)
        self._match_view = MatchView()
        self._statistics_view = StatisticsView(application.statistics)
        self._capture_view = CaptureView(application.capture, application.settings_manager)
        self._vision_view = VisionView(application.vision)
        self._rehearsal_view = RehearsalView(
            application.rehearsal_recorder,
            application.rehearsal_player,
            application.recordings_dir,
        )
        self._director_view = DirectorView(application.director)
        self._commentary_view = CommentaryView(application.play_by_play, application.analyst)
        self._voice_view = VoiceView(
            application.voice,
            application.obs,
            application.settings_manager,
            application.obs_scene_watcher,
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

        # Every view lives in the stack; the sidebar exposes them by role, grouped
        # into sections. "Train the AI" and "Team & Roles" live under an Admin
        # section that only appears for Staff+ / Admin+ — a plain User never sees it.
        _all = None  # visible to every role
        self._nav_sections: list[tuple[str, list]] = [
            ("Broadcast", [
                ("Dashboard", self._dashboard, _all),
                ("Voice, Audio & OBS", self._voice_view, _all),
                ("Replay", self._replay_view, _all),
                ("Rehearsal", self._rehearsal_view, _all),
            ]),
            ("Match & AI", [
                ("Live GSI", self._gsi_view, _all),
                ("Match Engine", self._match_view, _all),
                ("Statistics", self._statistics_view, _all),
                ("Commentary Director", self._director_view, _all),
                ("Commentary AIs", self._commentary_view, _all),
            ]),
            ("Video", [
                ("Video Capture", self._capture_view, _all),
                ("Computer Vision", self._vision_view, _all),
            ]),
            ("Admin", [
                ("Train the AI", self._training_view, can_train),
                ("Team & Roles", self._team_view, can_manage_roles),
            ]),
            ("System", [
                ("Account & License", self._account_view, _all),
                ("Diagnostics", self._diagnostics_view, _all),
                ("Settings", self._settings_view, _all),
            ]),
        ]
        for _title, items in self._nav_sections:
            for _label, widget, _access in items:
                self._stack.addWidget(widget)

        self._nav.currentItemChanged.connect(self._on_nav_item_changed)
        self._rebuild_nav()

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
        self._bridge.auth_state.connect(self._on_auth_state)
        self._bridge.license_state.connect(self._account_view.on_license_state)
        self._bridge.update_available.connect(self._account_view.on_update_available)
        self._bridge.diagnostics.connect(self._diagnostics_view.on_diagnostics)
        self._bridge.broadcast_state.connect(self._dashboard.on_broadcast_state)

        self.statusBar().showMessage(f"GSI endpoint: {application.gsi_server.address}")

    # ------------------------------------------------------------------ #
    # Role-gated, sectioned navigation
    # ------------------------------------------------------------------ #
    def _current_role(self) -> Role:
        account = self._app.auth.account
        return account.role_enum if account is not None else Role.USER

    def _rebuild_nav(self) -> None:
        """Rebuild the sidebar for the current role (admin items appear/vanish)."""
        role = self._current_role()
        keep = self._stack.currentWidget()
        self._nav.blockSignals(True)
        self._nav.clear()
        first_view_item = None
        for title, items in self._nav_sections:
            visible = [(label, w) for (label, w, access) in items if access is None or access(role)]
            if not visible:
                continue
            self._add_nav_header(title)
            for label, widget in visible:
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, widget)
                self._nav.addItem(item)
                if first_view_item is None:
                    first_view_item = item
        self._nav.blockSignals(False)
        # Keep the current view selected if it's still available; else land on the
        # first entry (Dashboard).
        if not self._select_widget_in_nav(keep) and first_view_item is not None:
            self._nav.setCurrentItem(first_view_item)

    def _add_nav_header(self, title: str) -> None:
        header = QListWidgetItem(title.upper())
        header.setFlags(Qt.ItemFlag.NoItemFlags)  # non-selectable label
        font = header.font()
        font.setBold(True)
        font.setPointSize(max(7, font.pointSize() - 1))
        header.setFont(font)
        header.setForeground(QColor(MUTED))
        self._nav.addItem(header)

    def _select_widget_in_nav(self, widget) -> bool:  # noqa: ANN001 - QWidget | None
        if widget is None:
            return False
        for i in range(self._nav.count()):
            item = self._nav.item(i)
            if item.data(Qt.ItemDataRole.UserRole) is widget:
                self._nav.setCurrentItem(item)
                return True
        return False

    def _on_nav_item_changed(self, current, _previous) -> None:  # noqa: ANN001 - QListWidgetItem
        if current is None:
            return
        widget = current.data(Qt.ItemDataRole.UserRole)
        if widget is not None:
            self._stack.setCurrentWidget(widget)

    # ------------------------------------------------------------------ #
    # Top-right account control
    # ------------------------------------------------------------------ #
    def _build_account_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("accountBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 4, 10, 4)
        row.addStretch(1)
        self._account_label = QLabel()
        self._account_label.setStyleSheet("color: #888;")
        self._account_button = QPushButton()
        self._account_button.clicked.connect(self._on_account_button)
        row.addWidget(self._account_label)
        row.addWidget(self._account_button)
        self._refresh_account_bar()
        return bar

    def _refresh_account_bar(self) -> None:
        account = self._app.auth.account
        if account is not None:
            from ai_caster.auth.roles import role_label

            self._account_label.setText(f"{account.label}  ·  {role_label(account.role_enum)}")
            self._account_button.setText("Sign out")
        else:
            self._account_label.setText("Not signed in")
            self._account_button.setText("Sign in")

    def _on_account_button(self) -> None:
        if self._app.auth.is_authenticated:
            self._app.auth.logout()  # -> auth-state event -> _on_auth_state -> prompt
        else:
            self._prompt_sign_in()

    def _on_auth_state(self, authenticated: bool, account, detail: str) -> None:  # noqa: ANN001
        self._refresh_account_bar()
        # Role may have changed (sign-in, role refresh) — reflect Admin visibility.
        self._rebuild_nav()
        # A sign-out drops the operator straight back to the login / sign-up window.
        if not authenticated and detail == "signed out":
            QTimer.singleShot(0, self._prompt_sign_in)

    def _prompt_sign_in(self) -> None:
        from ai_caster.ui.auth_window import require_sign_in

        if require_sign_in(self._app.auth):
            self._refresh_account_bar()
        else:
            # Accounts are required; a dismissed re-sign-in closes the app.
            _log.info("Re-sign-in dismissed; closing.")
            self.close()

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
    apply_theme(qt_app)

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
