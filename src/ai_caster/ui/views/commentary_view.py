"""Commentary view — the generated play-by-play and analyst lines.

Shows the two independent AI voices as a live transcript, with an enable toggle
per channel and the active provider. This is the text the Voice Engine (M7) will
speak.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from ai_caster.commentary.generator import CommentaryGenerator
from ai_caster.commentary.lines import CommentaryLine

_MAX_FEED = 200


class _ChannelPanel(QGroupBox):
    """One speaker channel: enable toggle + transcript."""

    def __init__(self, title: str, generator: CommentaryGenerator) -> None:
        super().__init__(title)
        self._generator = generator
        layout = QVBoxLayout(self)

        self._enable = QCheckBox("Enabled")
        self._enable.setChecked(True)
        self._enable.toggled.connect(generator.set_enabled)
        layout.addWidget(self._enable)

        self._feed = QListWidget()
        self._feed.setStyleSheet("font-size: 13px;")
        self._feed.setWordWrap(True)
        layout.addWidget(self._feed)

    def add_line(self, line: CommentaryLine) -> None:
        self._feed.insertItem(0, line.text)
        while self._feed.count() > _MAX_FEED:
            self._feed.takeItem(self._feed.count() - 1)


class CommentaryView(QWidget):
    """Live transcript of both commentary channels."""

    def __init__(self, play_by_play: CommentaryGenerator, analyst: CommentaryGenerator) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        title = QLabel("Commentary AIs")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)
        note = QLabel(
            "Two independent voices generated from confirmed match facts. "
            "Original wording; never imitating a real caster."
        )
        note.setStyleSheet("color: #888;")
        note.setWordWrap(True)
        root.addWidget(note)

        columns = QHBoxLayout()
        self._pbp = _ChannelPanel("Play-by-Play", play_by_play)
        self._analyst = _ChannelPanel("Analyst", analyst)
        columns.addWidget(self._pbp)
        columns.addWidget(self._analyst)
        root.addLayout(columns, stretch=1)

    # -- slot (Qt thread) ------------------------------------------------ #
    def on_commentary_line(self, line: CommentaryLine) -> None:
        if line is None:
            return
        if line.speaker == "analyst":
            self._analyst.add_line(line)
        else:
            self._pbp.add_line(line)
