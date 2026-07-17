"""Statistics view.

A live scoreboard-style table of the per-player statistics accumulated by the
:class:`~ai_caster.statistics.engine.StatisticsEngine`. Refreshed whenever the
match model updates.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ai_caster.statistics.engine import StatisticsEngine

_COLUMNS = ["Player", "Side", "K", "D", "A", "K/D", "ADR", "HS%", "Open", "Clutch", "MVP"]


class StatisticsView(QWidget):
    """Renders the current match statistics table."""

    def __init__(self, statistics: StatisticsEngine) -> None:
        super().__init__()
        self._statistics = statistics

        root = QVBoxLayout(self)
        title = QLabel("Statistics Engine")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._table)

        self._empty = QLabel("No statistics yet — waiting for match data.")
        self._empty.setStyleSheet("color: #888;")
        root.addWidget(self._empty)

    def refresh(self) -> None:
        """Rebuild the table from a snapshot of the statistics."""
        # Snapshot to a list so a concurrent engine update can't mutate mid-read.
        players = sorted(
            list(self._statistics.statistics.players.values()),
            key=lambda p: (p.kills, p.kd_diff),
            reverse=True,
        )
        self._empty.setVisible(not players)
        self._table.setRowCount(len(players))
        for row, p in enumerate(players):
            values = [
                p.name,
                p.side or "—",
                str(p.kills),
                str(p.deaths),
                str(p.assists),
                f"{p.kd_ratio:.2f}",
                f"{p.adr:.0f}",
                f"{p.headshot_pct:.0f}",
                str(p.opening_kills),
                str(p.clutches_won),
                str(p.mvps),
            ]
            for col, value in enumerate(values):
                self._table.setItem(row, col, QTableWidgetItem(value))
