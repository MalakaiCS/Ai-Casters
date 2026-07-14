"""Video capture view.

Controls the :class:`~ai_caster.capture.pipeline.CapturePipeline` (start/stop),
shows live capture statistics, and renders a low-rate preview of the most recent
frame. The preview is refreshed on the ~1 Hz stats tick — not per frame — so the
UI never competes with the capture loop.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_caster.capture.pipeline import CapturePipeline
from ai_caster.capture.timing import CaptureStats


class CaptureView(QWidget):
    """Start/stop capture, view stats, and preview the latest frame."""

    def __init__(self, pipeline: CapturePipeline) -> None:
        super().__init__()
        self._pipeline = pipeline

        root = QVBoxLayout(self)
        title = QLabel("Video Capture")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        # Controls.
        controls = QHBoxLayout()
        self._start_btn = QPushButton("Start capture")
        self._start_btn.clicked.connect(self._on_start)
        self._stop_btn = QPushButton("Stop capture")
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setEnabled(False)
        controls.addWidget(self._start_btn)
        controls.addWidget(self._stop_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        # Stats.
        stats_box = QGroupBox("Capture statistics")
        form = QFormLayout(stats_box)
        self._source = QLabel(pipeline.source.name)
        self._state = QLabel("Stopped")
        self._fps = QLabel("—")
        self._frames = QLabel("—")
        self._dropped = QLabel("—")
        self._latency = QLabel("—")
        self._device = QLabel(pipeline.device)
        form.addRow("Source:", self._source)
        form.addRow("State:", self._state)
        form.addRow("FPS (actual / target):", self._fps)
        form.addRow("Frames captured:", self._frames)
        form.addRow("Frames dropped:", self._dropped)
        form.addRow("Avg capture latency:", self._latency)
        form.addRow("Frame device:", self._device)
        root.addWidget(stats_box)

        # Preview.
        preview_box = QGroupBox("Preview (updates ~1/s)")
        preview_layout = QVBoxLayout(preview_box)
        self._preview = QLabel("No frames yet.")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(240)
        self._preview.setStyleSheet("background: #111; color: #888;")
        preview_layout.addWidget(self._preview)
        root.addWidget(preview_box, stretch=1)

    # -- button handlers -------------------------------------------------- #
    def _on_start(self) -> None:
        try:
            self._pipeline.start()
        except Exception as exc:  # noqa: BLE001 - report source-open failures
            QMessageBox.critical(self, "Capture error", f"Could not start capture:\n{exc}")

    def _on_stop(self) -> None:
        self._pipeline.stop()

    # -- slots (Qt thread) ------------------------------------------------ #
    def on_capture_status(self, running: bool, source: str, detail: str) -> None:
        self._state.setText(f"Running ({detail})" if running else f"Stopped ({detail})")
        self._state.setStyleSheet(f"color: {'#44cc66' if running else '#cc9944'};")
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        if not running:
            self._preview.setText("No frames yet.")

    def on_capture_stats(self, stats: CaptureStats) -> None:
        if stats is None:
            return
        self._fps.setText(f"{stats.actual_fps:.1f} / {stats.target_fps:.0f}")
        self._frames.setText(str(stats.frames_captured))
        self._dropped.setText(f"{stats.frames_dropped}  ({stats.drop_rate * 100:.1f}%)")
        self._latency.setText(f"{stats.avg_capture_ms:.2f} ms")
        self._render_preview()

    def _render_preview(self) -> None:
        frame = self._pipeline.latest_frame()
        if frame is None or not frame.is_valid:
            return
        image = QImage(
            frame.to_rgb_bytes(),
            frame.width,
            frame.height,
            frame.width * 3,
            QImage.Format.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(image).scaled(
            self._preview.width(),
            self._preview.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview.setPixmap(pixmap)
