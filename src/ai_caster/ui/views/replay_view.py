"""Replay integration view.

Shows the current replay state and lets the operator inject replay events locally
for testing (the real events arrive over HTTP from the external replay system).
Feeding the receiver directly here is equivalent to a POST to the replay server.
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

from ai_caster.replay.models import ReplayState
from ai_caster.replay.receiver import ReplayReceiver


class ReplayView(QWidget):
    """Displays replay state and provides local test controls."""

    def __init__(self, receiver: ReplayReceiver, listen_address: str) -> None:
        super().__init__()
        self._receiver = receiver

        root = QVBoxLayout(self)
        title = QLabel("Replay Integration")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)
        note = QLabel(
            "The replay system runs externally and POSTs events to "
            f"<b>{listen_address}</b>. The AI never describes replay footage as live."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        root.addWidget(note)

        state_box = QGroupBox("Replay state")
        form = QFormLayout(state_box)
        self._active = QLabel("—")
        self._type = QLabel("—")
        self._speed = QLabel("—")
        form.addRow("Active:", self._active)
        form.addRow("Type:", self._type)
        form.addRow("Speed:", self._speed)
        root.addWidget(state_box)

        controls = QGroupBox("Local test controls")
        controls_layout = QHBoxLayout(controls)
        for label, payload in (
            ("Kill replay", {"event": "started", "type": "kill", "speed": 1.0}),
            ("Clutch replay", {"event": "started", "type": "clutch", "speed": 0.5}),
            ("End replay", {"event": "ended"}),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, p=payload: self._inject(p))
            controls_layout.addWidget(button)
        root.addWidget(controls)
        root.addStretch(1)

        self._update(receiver.state)

    def _inject(self, payload: dict) -> None:
        try:
            self._receiver.handle_event(payload)
        except Exception:  # noqa: BLE001 - test control, ignore malformed
            pass

    # -- slot (Qt thread) ------------------------------------------------ #
    def on_replay_state(self, state: ReplayState, _transition: str) -> None:
        self._update(state)

    def _update(self, state: ReplayState) -> None:
        self._active.setText("Yes" if state.active else "No")
        self._active.setStyleSheet(f"color: {'#cc9944' if state.active else '#44cc66'};")
        self._type.setText(state.replay_type.value)
        self._speed.setText(f"{state.speed:.2f}x")
