"""A placeholder view for modules that land in later milestones.

Every future module gets a navigable entry from day one so the shell shows the
full product surface and later work slots in without restructuring navigation.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderView(QWidget):
    """Shows a module title and the milestone that will implement it."""

    def __init__(self, title: str, milestone: str, description: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        heading = QLabel(title)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")

        badge = QLabel(f"Planned — {milestone}")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet("color: #888; font-size: 13px;")

        layout.addWidget(heading)
        layout.addWidget(badge)

        if description:
            body = QLabel(description)
            body.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body.setWordWrap(True)
            body.setStyleSheet("color: #aaa; font-size: 13px; margin-top: 12px;")
            layout.addWidget(body)
