"""Live match view.

Renders the Match State Engine's :class:`~ai_caster.match.model.LiveMatch` — the
single source of truth — and a live feed of detected events. Updates arrive via
the :class:`~ai_caster.ui.qt_event_bridge.QtEventBridge` on the Qt thread.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ai_caster.detection.events import (
    BombDefused,
    BombExploded,
    BombPlanted,
    ClutchStarted,
    ClutchWon,
    Kill,
    MatchEnded,
    MatchEvent,
    MatchStarted,
    PlayerDeath,
    RoundEnded,
    RoundStarted,
)
from ai_caster.match.model import LiveMatch

_MAX_FEED_ITEMS = 200


def describe_event(event: MatchEvent) -> str:
    """Human-readable one-liner for the event feed."""
    r = f"R{event.round_number + 1}"
    if isinstance(event, MatchStarted):
        return f"{r}  ▶ Match started on {event.map_name}"
    if isinstance(event, MatchEnded):
        return f"{r}  ⏹ Match over — {event.winner} wins {event.ct_score}-{event.t_score}"
    if isinstance(event, RoundStarted):
        return f"{r}  ● Round live"
    if isinstance(event, RoundEnded):
        return f"{r}  ◆ Round to {event.winner} ({event.reason})"
    if isinstance(event, Kill):
        tags = []
        if event.is_entry:
            tags.append("entry")
        if event.is_trade:
            tags.append("trade")
        if event.headshot:
            tags.append("HS")
        victim = f" → {event.victim_name}" if event.victim_name else ""
        suffix = f" [{', '.join(tags)}]" if tags else ""
        return f"{r}  ✱ {event.killer_name} kill{victim}{suffix}"
    if isinstance(event, PlayerDeath):
        return f"{r}  ☠ {event.victim_name} down"
    if isinstance(event, BombPlanted):
        return f"{r}  ✸ Bomb planted"
    if isinstance(event, BombDefused):
        return f"{r}  ✂ Bomb defused"
    if isinstance(event, BombExploded):
        return f"{r}  💥 Bomb exploded"
    if isinstance(event, ClutchStarted):
        return f"{r}  ♦ {event.player_name} in a 1v{event.opponents_alive} clutch"
    if isinstance(event, ClutchWon):
        return f"{r}  ♛ {event.player_name} WON the 1v{event.opponents_beaten} clutch"
    return f"{r}  {type(event).__name__}"


class MatchView(QWidget):
    """Displays the live match model and the detected-event feed."""

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)

        title = QLabel("Match State Engine — single source of truth")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        # Scoreboard row.
        board = QGroupBox("Scoreboard")
        board_form = QFormLayout(board)
        self._score = QLabel("—")
        self._score.setStyleSheet("font-size: 20px; font-weight: 700;")
        self._round = QLabel("—")
        self._phase = QLabel("—")
        self._alive = QLabel("—")
        self._economy = QLabel("—")
        board_form.addRow("Score (CT–T):", self._score)
        board_form.addRow("Round:", self._round)
        board_form.addRow("Phase / bomb:", self._phase)
        board_form.addRow("Alive (CT/T):", self._alive)
        board_form.addRow("Economy:", self._economy)
        root.addWidget(board)

        # Momentum + importance.
        meters = QGroupBox("Read")
        meters_layout = QFormLayout(meters)
        self._momentum = QProgressBar()
        self._momentum.setRange(-100, 100)
        self._momentum.setValue(0)
        self._momentum.setFormat("%v")
        self._round_importance = QProgressBar()
        self._round_importance.setRange(0, 100)
        self._series_importance = QProgressBar()
        self._series_importance.setRange(0, 100)
        meters_layout.addRow("Momentum (T ◀ ▶ CT):", self._momentum)
        meters_layout.addRow("Round importance:", self._round_importance)
        meters_layout.addRow("Series importance:", self._series_importance)
        root.addWidget(meters)

        # Event feed.
        feed_box = QGroupBox("Event feed")
        feed_layout = QVBoxLayout(feed_box)
        self._feed = QListWidget()
        self._feed.setStyleSheet("font-family: monospace; font-size: 12px;")
        feed_layout.addWidget(self._feed)
        root.addWidget(feed_box, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self._map = QLabel("—")
        self._map.setStyleSheet("color: #888;")
        footer.addWidget(self._map)
        root.addLayout(footer)

    # -- slots (Qt thread) ------------------------------------------------ #
    def on_match_updated(self, match: LiveMatch) -> None:
        if match is None:
            return
        self._map.setText(match.map_name or "—")
        self._score.setText(f"{match.ct.score} – {match.t.score}")
        rounds_played = len(match.history)
        self._round.setText(f"{match.round_number + 1}  ({rounds_played} played)")
        self._phase.setText(f"{match.round_phase or '—'} / {match.bomb_state or '—'}")
        self._alive.setText(f"{match.ct.players_alive} / {match.t.players_alive}")
        self._economy.setText(
            f"CT ${match.ct.money} ({match.ct.buy_type})   T ${match.t.money} ({match.t.buy_type})"
        )
        self._momentum.setValue(int(match.momentum.value * 100))
        self._round_importance.setValue(int(match.round_importance * 100))
        self._series_importance.setValue(int(match.series_importance * 100))

    def on_match_event(self, event: MatchEvent) -> None:
        self._feed.insertItem(0, describe_event(event))
        while self._feed.count() > _MAX_FEED_ITEMS:
            self._feed.takeItem(self._feed.count() - 1)
