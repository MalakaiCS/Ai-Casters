"""Live GSI monitor view.

Displays the latest parsed CS2 Game State Integration data in real time. It
connects to the :class:`~ai_caster.ui.qt_event_bridge.QtEventBridge` signals so
updates always arrive on the Qt thread.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai_caster.gsi.models import GameState


class GSIView(QWidget):
    """Real-time view of the incoming GSI feed."""

    def __init__(self, address: str) -> None:
        super().__init__()
        self._payloads = 0

        root = QVBoxLayout(self)

        # Connection status strip.
        status_row = QHBoxLayout()
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #cc4444; font-size: 16px;")
        self._status_text = QLabel("Waiting for CS2 GSI feed…")
        self._addr = QLabel(f"Listening: {address}")
        self._addr.setStyleSheet("color: #888;")
        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status_text)
        status_row.addStretch(1)
        status_row.addWidget(self._addr)
        root.addLayout(status_row)

        # Headline match fields.
        summary = QGroupBox("Match")
        form = QFormLayout(summary)
        self._map = QLabel("—")
        self._phase = QLabel("—")
        self._round = QLabel("—")
        self._score = QLabel("—")
        self._bomb = QLabel("—")
        self._observed = QLabel("—")
        self._alive = QLabel("—")
        form.addRow("Map:", self._map)
        form.addRow("Match phase:", self._phase)
        form.addRow("Round:", self._round)
        form.addRow("Score (CT–T):", self._score)
        form.addRow("Bomb:", self._bomb)
        form.addRow("Observed player:", self._observed)
        form.addRow("Players alive:", self._alive)
        root.addWidget(summary)

        # Raw payload viewer for diagnostics.
        raw_box = QGroupBox("Latest payload (parsed)")
        raw_layout = QVBoxLayout(raw_box)
        self._raw = QPlainTextEdit()
        self._raw.setReadOnly(True)
        self._raw.setPlaceholderText("Parsed GSI JSON will appear here as it arrives.")
        self._raw.setStyleSheet("font-family: monospace; font-size: 12px;")
        raw_layout.addWidget(self._raw)
        root.addWidget(raw_box, stretch=1)

        self._counter = QLabel("0 payloads received")
        self._counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._counter.setStyleSheet("color: #888;")
        root.addWidget(self._counter)

    # -- slots (Qt thread) ------------------------------------------------ #
    def on_connection_changed(self, connected: bool, detail: str) -> None:
        if connected:
            self._status_dot.setStyleSheet("color: #44cc66; font-size: 16px;")
            self._status_text.setText(detail or "Connected")
        else:
            self._status_dot.setStyleSheet("color: #cc4444; font-size: 16px;")
            self._status_text.setText(detail or "Disconnected")

    def on_gsi_state(self, state: GameState) -> None:
        self._payloads += 1
        self._map.setText(state.map_name or "—")
        self._phase.setText((state.map.phase if state.map else None) or "—")
        self._round.setText(
            "—" if state.round_number is None else str(state.round_number + 1)
        )
        ct = "—" if state.ct_score is None else str(state.ct_score)
        t = "—" if state.t_score is None else str(state.t_score)
        self._score.setText(f"{ct} – {t}")
        self._bomb.setText((state.round.bomb if state.round else None) or "—")
        self._observed.setText(state.observed_player_name or "—")

        alive = "—"
        if state.allplayers:
            alive = str(
                sum(
                    1
                    for p in state.allplayers.values()
                    if p.state is not None and (p.state.health or 0) > 0
                )
            )
        self._alive.setText(alive)

        self._raw.setPlainText(state.model_dump_json(indent=2, exclude_none=True))
        self._counter.setText(f"{self._payloads} payloads received")
