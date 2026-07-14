"""Dashboard / home view.

A high-level status overview: which core services are running, the GSI feed
state, and quick orientation for the operator. Expands as modules come online.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ai_caster import __version__


class DashboardView(QWidget):
    """At-a-glance status of the application."""

    def __init__(self, gsi_address: str) -> None:
        super().__init__()
        root = QVBoxLayout(self)

        title = QLabel("AI Esports Caster")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel(f"Milestone 1 — Foundation · v{__version__}")
        subtitle.setStyleSheet("color: #888;")
        root.addWidget(title)
        root.addWidget(subtitle)

        status = QGroupBox("Core services")
        form = QFormLayout(status)
        self._gsi_status = QLabel("Starting…")
        form.addRow("GSI receiver:", self._gsi_status)
        form.addRow("GSI endpoint:", QLabel(gsi_address))
        self._feed_status = QLabel("Waiting for CS2…")
        form.addRow("GSI feed:", self._feed_status)
        root.addWidget(status)

        hint = QLabel(
            "Configure and connect CS2 from the <b>Settings → GSI</b> section, "
            "then generate the game config. Live data appears in <b>Live GSI</b>."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa; margin-top: 8px;")
        root.addWidget(hint)

        root.addStretch(1)
        footer = QLabel("Later milestones add vision, commentary AI, voice, OBS and licensing.")
        footer.setAlignment(Qt.AlignmentFlag.AlignBottom)
        footer.setStyleSheet("color: #777; font-size: 12px;")
        root.addWidget(footer)

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
