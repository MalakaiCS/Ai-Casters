"""Rehearsal view — record a live match and replay it to test the whole cast.

Two panels:

* **Record** captures the live GSI feed to a ``.jsonl`` clip (auth token stripped).
* **Replay** loads a clip and feeds it back through the real pipeline at a chosen
  speed, so the match model, director, banter and voices all run exactly as they
  would live — no CS2 required. Ideal for tuning voices and tone against a real
  match before going on air.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_caster.rehearsal.player import RehearsalPlayer, load_clip
from ai_caster.rehearsal.recorder import GsiRecorder

_SPEEDS = [("0.5×", 0.5), ("1×", 1.0), ("2×", 2.0), ("4×", 4.0), ("Instant", 0.0)]


class RehearsalView(QWidget):
    """Record and replay GSI clips."""

    # Player callbacks fire on a worker thread; marshal them to the UI thread.
    _progress = Signal(int, int)
    _finished = Signal(bool)

    def __init__(
        self,
        recorder: GsiRecorder,
        player: RehearsalPlayer,
        recordings_dir: Path,
    ) -> None:
        super().__init__()
        self._recorder = recorder
        self._player = player
        self._dir = Path(recordings_dir)
        self._clip = None

        # Route the player's thread-side callbacks onto our signals so the UI is
        # only ever touched on the Qt thread.
        self._player.set_callbacks(
            on_progress=self._progress.emit, on_finished=self._finished.emit
        )
        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)

        root = QVBoxLayout(self)
        title = QLabel("Rehearsal — record & replay a match")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)
        blurb = QLabel(
            "Record a live match once, then replay it any time to hear the full cast "
            "— commentary, banter and voices — without CS2 running. Perfect for tuning."
        )
        blurb.setWordWrap(True)
        blurb.setStyleSheet("color: #888;")
        root.addWidget(blurb)

        # -- record ------------------------------------------------------- #
        record_box = QGroupBox("Record the live feed")
        record_layout = QHBoxLayout(record_box)
        self._record_btn = QPushButton("Start recording")
        self._record_btn.clicked.connect(self._on_toggle_record)
        self._record_status = QLabel("Not recording.")
        self._record_status.setStyleSheet("color: #888;")
        record_layout.addWidget(self._record_btn)
        record_layout.addWidget(self._record_status, stretch=1)
        root.addWidget(record_box)

        # -- replay ------------------------------------------------------- #
        replay_box = QGroupBox("Replay a recording")
        replay_layout = QVBoxLayout(replay_box)

        pick_row = QHBoxLayout()
        self._load_btn = QPushButton("Load clip…")
        self._load_btn.clicked.connect(self._on_load)
        self._clip_label = QLabel("No clip loaded.")
        self._clip_label.setStyleSheet("color: #888;")
        pick_row.addWidget(self._load_btn)
        pick_row.addWidget(self._clip_label, stretch=1)
        replay_layout.addLayout(pick_row)

        control_row = QHBoxLayout()
        self._speed = QComboBox()
        for label, value in _SPEEDS:
            self._speed.addItem(label, value)
        self._speed.setCurrentIndex(1)  # 1×
        self._play_btn = QPushButton("Play")
        self._play_btn.clicked.connect(self._on_play)
        self._play_btn.setEnabled(False)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setEnabled(False)
        control_row.addWidget(QLabel("Speed:"))
        control_row.addWidget(self._speed)
        control_row.addWidget(self._play_btn)
        control_row.addWidget(self._stop_btn)
        control_row.addStretch(1)
        replay_layout.addLayout(control_row)

        self._progress_bar = QProgressBar()
        self._progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_bar.setFormat("%v / %m frames")
        replay_layout.addWidget(self._progress_bar)
        root.addWidget(replay_box)
        root.addStretch(1)

    # -- record handlers -------------------------------------------------- #
    def _on_toggle_record(self) -> None:
        if self._recorder.is_recording:
            path = self._recorder.stop()
            self._record_btn.setText("Start recording")
            frames = self._recorder.frame_count
            self._record_status.setText(
                f"Saved {frames} frames to {path.name}" if path else "Stopped."
            )
            return
        default = self._dir / f"match-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save recording", str(default), "Rehearsal clips (*.jsonl)"
        )
        if not path:
            return
        try:
            self._recorder.start(path)
        except OSError as exc:
            QMessageBox.critical(self, "Recording error", f"Could not start recording:\n{exc}")
            return
        self._record_btn.setText("Stop recording")
        self._record_status.setText(
            "Recording live GSI… play a match (or the demo) and press Stop when done."
        )

    # -- replay handlers -------------------------------------------------- #
    def _on_load(self) -> None:
        start_dir = str(self._dir if self._dir.exists() else Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Load recording", start_dir, "Rehearsal clips (*.jsonl)"
        )
        if not path:
            return
        try:
            clip = load_clip(path)
        except OSError as exc:
            QMessageBox.critical(self, "Load error", f"Could not read the clip:\n{exc}")
            return
        if not clip.frames:
            QMessageBox.warning(self, "Empty clip", "That file has no usable frames.")
            return
        self._clip = clip
        self._clip_label.setText(
            f"{Path(path).name} — {len(clip)} frames, {clip.duration:.0f}s"
        )
        self._progress_bar.setMaximum(len(clip))
        self._progress_bar.setValue(0)
        self._play_btn.setEnabled(True)

    def _on_play(self) -> None:
        if self._clip is None or self._player.is_playing:
            return
        speed = float(self._speed.currentData())
        self._player.play(self._clip, speed=speed)
        self._play_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._load_btn.setEnabled(False)

    def _on_stop(self) -> None:
        self._player.stop()
        self._reset_controls()

    # -- signal slots (UI thread) ---------------------------------------- #
    def _on_progress(self, played: int, total: int) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(played)

    def _on_finished(self, completed: bool) -> None:
        self._reset_controls()

    def _reset_controls(self) -> None:
        self._play_btn.setEnabled(self._clip is not None)
        self._stop_btn.setEnabled(False)
        self._load_btn.setEnabled(True)
