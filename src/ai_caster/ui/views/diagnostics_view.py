"""Diagnostics dashboard view (Milestone 9).

Live runtime health — uptime, GSI/casting state, capture/vision/voice metrics,
CPU/memory and event throughput — plus an in-app tail of the application log.
Metrics refresh from :class:`DiagnosticsUpdated` events marshalled onto the Qt
thread; the log tail is read on demand.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_caster.diagnostics.logs import tail_log
from ai_caster.diagnostics.models import DiagnosticsSnapshot


class DiagnosticsView(QWidget):
    """Runtime metrics and log inspector."""

    def __init__(self, log_dir: Path | None, *, log_tail_lines: int = 200) -> None:
        super().__init__()
        self._log_dir = log_dir
        self._log_tail_lines = log_tail_lines

        root = QVBoxLayout(self)
        title = QLabel("Diagnostics")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        metrics = QGroupBox("Runtime health")
        form = QFormLayout(metrics)
        self._uptime = QLabel("—")
        self._state = QLabel("—")
        self._capture = QLabel("—")
        self._vision = QLabel("—")
        self._voice = QLabel("—")
        self._resources = QLabel("—")
        self._events = QLabel("—")
        form.addRow("Uptime:", self._uptime)
        form.addRow("State:", self._state)
        form.addRow("Capture:", self._capture)
        form.addRow("Vision:", self._vision)
        form.addRow("Voice queues:", self._voice)
        form.addRow("Resources:", self._resources)
        form.addRow("Events seen:", self._events)
        root.addWidget(metrics)

        logs = QGroupBox("Application log")
        log_layout = QVBoxLayout(logs)
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("monospace"))
        self._log_view.setMaximumBlockCount(self._log_tail_lines + 50)
        refresh = QPushButton("Refresh log")
        refresh.clicked.connect(self.refresh_log)
        log_layout.addWidget(self._log_view)
        log_layout.addWidget(refresh)
        root.addWidget(logs, stretch=1)

        self.refresh_log()

    # ------------------------------------------------------------------ #
    def refresh_log(self) -> None:
        lines = tail_log(self._log_dir, lines=self._log_tail_lines)
        self._log_view.setPlainText("\n".join(lines))

    @staticmethod
    def _fmt(value: float | None, suffix: str) -> str:
        return f"{value:.0f}{suffix}" if value is not None else "n/a"

    # -- slot (Qt thread) ------------------------------------------------ #
    def on_diagnostics(self, snapshot: DiagnosticsSnapshot) -> None:
        if snapshot is None:
            return
        self._uptime.setText(snapshot.uptime_clock)
        casting = "casting" if snapshot.casting else "idle"
        muted = "  ·  muted" if snapshot.muted else ""
        replay = "  ·  REPLAY" if snapshot.replay_active else ""
        feed = "GSI connected" if snapshot.gsi_connected else "GSI waiting"
        self._state.setText(f"{casting}{muted}{replay}  ·  {feed}")
        self._capture.setText(
            f"{'running' if snapshot.capture_running else 'stopped'}  ·  "
            f"{snapshot.capture_fps:.0f} fps  ·  drop {snapshot.capture_drop_rate * 100:.1f}%"
        )
        self._vision.setText(
            f"{'on' if snapshot.vision_enabled else 'off'}  ·  "
            f"{snapshot.vision_processed} frames analysed"
        )
        self._voice.setText(
            f"play-by-play {snapshot.voice_pending_play_by_play}  ·  "
            f"analyst {snapshot.voice_pending_analyst}"
        )
        self._resources.setText(
            f"CPU {self._fmt(snapshot.cpu_percent, '%')}  ·  "
            f"memory {self._fmt(snapshot.memory_mb, ' MB')}"
        )
        self._events.setText(str(snapshot.event_count))
