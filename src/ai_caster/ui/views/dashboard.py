"""Dashboard / home view.

A high-level status overview plus the top-level broadcast controls (go live,
master mute, force replay) — the same actions the global hotkeys drive. Reflects
core-service and feed state at a glance.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_caster import __version__
from ai_caster.broadcast.controller import BroadcastController


class DashboardView(QWidget):
    """At-a-glance status of the application, plus broadcast controls."""

    def __init__(self, gsi_address: str, broadcast: BroadcastController | None = None) -> None:
        super().__init__()
        self._broadcast = broadcast
        root = QVBoxLayout(self)

        title = QLabel("AI Esports Caster")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel(f"Autonomous CS2 commentary · v{__version__}")
        subtitle.setStyleSheet("color: #888;")
        root.addWidget(title)
        root.addWidget(subtitle)

        if broadcast is not None:
            root.addWidget(self._build_broadcast_box(broadcast))

        status = QGroupBox("Core services")
        form = QFormLayout(status)
        self._gsi_status = QLabel("Starting…")
        form.addRow("GSI receiver:", self._gsi_status)
        form.addRow("GSI endpoint:", QLabel(gsi_address))
        self._feed_status = QLabel("Waiting for CS2…")
        form.addRow("GSI feed:", self._feed_status)
        root.addWidget(status)

        hint = QLabel(
            "Sign in under <b>Account &amp; License</b>, connect CS2 from "
            "<b>Settings → GSI</b>, then press <b>Go live</b>. Watch runtime health "
            "in <b>Diagnostics</b>."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa; margin-top: 8px;")
        root.addWidget(hint)

        root.addStretch(1)

    # ------------------------------------------------------------------ #
    def _build_broadcast_box(self, broadcast: BroadcastController) -> QGroupBox:
        box = QGroupBox("Broadcast")
        layout = QVBoxLayout(box)

        self._broadcast_state = QLabel("Idle")
        self._broadcast_state.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(self._broadcast_state)

        buttons = QHBoxLayout()
        self._go_live = QPushButton("Go live")
        self._go_live.clicked.connect(broadcast.toggle_casting)
        self._mute = QPushButton("Mute all")
        self._mute.clicked.connect(broadcast.toggle_mute)
        self._replay = QPushButton("Force replay")
        self._replay.clicked.connect(broadcast.toggle_forced_replay)
        buttons.addWidget(self._go_live)
        buttons.addWidget(self._mute)
        buttons.addWidget(self._replay)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return box

    # ------------------------------------------------------------------ #
    # Slots (Qt thread)
    # ------------------------------------------------------------------ #
    def set_gsi_running(self, running: bool) -> None:
        self._gsi_status.setText("Running" if running else "Stopped")
        self._gsi_status.setStyleSheet(f"color: {'#44cc66' if running else '#cc4444'};")

    def set_feed_connected(self, connected: bool, detail: str = "") -> None:
        if connected:
            self._feed_status.setText(detail or "Connected")
            self._feed_status.setStyleSheet("color: #44cc66;")
        else:
            self._feed_status.setText(detail or "Waiting for CS2…")
            self._feed_status.setStyleSheet("color: #cc9944;")

    def on_broadcast_state(self, casting: bool, muted: bool, detail: str) -> None:
        if not hasattr(self, "_broadcast_state"):
            return
        state = "● LIVE" if casting else "Idle"
        if muted:
            state += "  ·  muted"
        self._broadcast_state.setText(state)
        self._broadcast_state.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {'#44cc66' if casting else '#aaa'};"
        )
        self._go_live.setText("Stop" if casting else "Go live")
        self._mute.setText("Unmute" if muted else "Mute all")
