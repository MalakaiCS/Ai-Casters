"""Commentary Director view.

Shows live broadcast state (live vs. replay) and a feed of the directives the
Director issues — who it wants to speak, about what, how urgently, and whether a
directive interrupts. The Director decides; this view makes those decisions
visible.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from ai_caster.director.directives import CommentaryDirective, DirectiveKind, Speaker
from ai_caster.director.director import CommentaryDirector

_MAX_FEED = 200

_SPEAKER_LABEL = {
    Speaker.PLAY_BY_PLAY: "Play-by-Play",
    Speaker.ANALYST: "Analyst",
    Speaker.NONE: "—",
}


def describe_directive(directive: CommentaryDirective) -> str:
    """One-line description of a directive for the feed."""
    if directive.is_silence:
        return f"⏸ SILENCE ({directive.reason or 'no comment'})"
    speaker = _SPEAKER_LABEL.get(directive.speaker, directive.speaker.value)
    bang = "  ‼INTERRUPT" if directive.interrupt else ""
    excite = "▮" * max(1, round(directive.excitement * 5))
    return f"{speaker} · {directive.kind.value} · {directive.topic}  [{excite}]{bang}"


class DirectorView(QWidget):
    """Displays broadcast flow state and the directive feed."""

    def __init__(self, director: CommentaryDirector) -> None:
        super().__init__()
        self._director = director

        root = QVBoxLayout(self)
        title = QLabel("Commentary Director")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)
        subtitle = QLabel("Decides broadcast flow — it never speaks. Words come from the AIs (M6).")
        subtitle.setStyleSheet("color: #888;")
        root.addWidget(subtitle)

        state_box = QGroupBox("Broadcast state")
        form = QFormLayout(state_box)
        self._live = QLabel("—")
        self._last_speaker = QLabel("—")
        form.addRow("Feed:", self._live)
        form.addRow("Last directed speaker:", self._last_speaker)
        root.addWidget(state_box)

        feed_box = QGroupBox("Directive feed")
        feed_layout = QVBoxLayout(feed_box)
        self._feed = QListWidget()
        self._feed.setStyleSheet("font-family: monospace; font-size: 12px;")
        feed_layout.addWidget(self._feed)
        root.addWidget(feed_box, stretch=1)

        self._refresh_live()

    # -- slots (Qt thread) ------------------------------------------------ #
    def on_directive(self, directive: CommentaryDirective) -> None:
        if directive is None:
            return
        self._feed.insertItem(0, describe_directive(directive))
        while self._feed.count() > _MAX_FEED:
            self._feed.takeItem(self._feed.count() - 1)
        if not directive.is_silence and directive.kind is not DirectiveKind.HANDOFF:
            self._last_speaker.setText(_SPEAKER_LABEL.get(directive.speaker, "—"))

    def on_replay_state(self, _state, _transition: str) -> None:
        self._refresh_live()

    def _refresh_live(self) -> None:
        live = self._director.is_live
        self._live.setText("LIVE" if live else "REPLAY (not live)")
        self._live.setStyleSheet(f"color: {'#44cc66' if live else '#cc9944'}; font-weight: 600;")
