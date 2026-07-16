"""Video capture view.

Controls the :class:`~ai_caster.capture.pipeline.CapturePipeline` (start/stop),
lets the operator pick which source/monitor to capture, shows live capture
statistics, and renders a preview of what the pipeline is looking at. The preview
refreshes on the ~1 Hz stats tick while running, and can be grabbed on demand
(a snapshot) while stopped — so you can confirm you've selected the right monitor
before going live.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_caster.capture.backends.monitor import available_monitors
from ai_caster.capture.factory import create_frame_source
from ai_caster.capture.pipeline import CapturePipeline
from ai_caster.capture.timing import CaptureStats
from ai_caster.config.manager import SettingsManager
from ai_caster.config.models import CaptureSourceType

_SOURCE_LABELS = {
    CaptureSourceType.MONITOR: "Monitor / screen",
    CaptureSourceType.WINDOW: "Window (by title)",
    CaptureSourceType.CAPTURE_CARD: "Capture card",
    CaptureSourceType.SYNTHETIC: "Synthetic (test pattern)",
}


class CaptureView(QWidget):
    """Pick a source/monitor, start/stop capture, view stats, and preview frames."""

    def __init__(self, pipeline: CapturePipeline, settings_manager: SettingsManager) -> None:
        super().__init__()
        self._pipeline = pipeline
        self._manager = settings_manager

        root = QVBoxLayout(self)
        title = QLabel("Video Capture")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        # -- source selection --------------------------------------------- #
        source_box = QGroupBox("Source")
        source_form = QFormLayout(source_box)
        self._source_combo = QComboBox()
        for source_type in (
            CaptureSourceType.MONITOR,
            CaptureSourceType.WINDOW,
            CaptureSourceType.CAPTURE_CARD,
            CaptureSourceType.SYNTHETIC,
        ):
            self._source_combo.addItem(_SOURCE_LABELS[source_type], source_type.value)
        self._source_combo.currentIndexChanged.connect(self._on_source_type_changed)

        self._monitor_combo = QComboBox()
        self._refresh_monitors_btn = QPushButton("Rescan")
        self._refresh_monitors_btn.setToolTip("Re-detect connected monitors.")
        self._refresh_monitors_btn.clicked.connect(self._populate_monitors)
        monitor_row = QHBoxLayout()
        monitor_row.addWidget(self._monitor_combo, stretch=1)
        monitor_row.addWidget(self._refresh_monitors_btn)
        self._monitor_row_widget = QWidget()
        self._monitor_row_widget.setLayout(monitor_row)

        source_form.addRow("Capture from:", self._source_combo)
        source_form.addRow("Monitor:", self._monitor_row_widget)

        apply_row = QHBoxLayout()
        self._apply_btn = QPushButton("Apply source")
        self._apply_btn.clicked.connect(self._on_apply_source)
        self._snapshot_btn = QPushButton("Refresh preview")
        self._snapshot_btn.setToolTip("Grab a single frame from the selected source.")
        self._snapshot_btn.clicked.connect(self._on_snapshot)
        apply_row.addWidget(self._apply_btn)
        apply_row.addWidget(self._snapshot_btn)
        apply_row.addStretch(1)
        source_form.addRow("", self._wrap(apply_row))
        root.addWidget(source_box)

        # -- start/stop --------------------------------------------------- #
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

        # -- stats -------------------------------------------------------- #
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

        # -- preview ------------------------------------------------------ #
        preview_box = QGroupBox("Preview — what the caster sees")
        preview_layout = QVBoxLayout(preview_box)
        self._preview = QLabel("No frames yet. Pick a source and click “Refresh preview”.")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(240)
        self._preview.setStyleSheet("background: #111; color: #888;")
        preview_layout.addWidget(self._preview)
        root.addWidget(preview_box, stretch=1)

        self._load_from_settings()

    # -- helpers ---------------------------------------------------------- #
    @staticmethod
    def _wrap(layout) -> QWidget:  # noqa: ANN001 - Qt layout
        holder = QWidget()
        holder.setLayout(layout)
        return holder

    def _load_from_settings(self) -> None:
        capture = self._manager.settings.capture
        idx = self._source_combo.findData(capture.source.value)
        if idx >= 0:
            self._source_combo.setCurrentIndex(idx)
        self._populate_monitors()
        self._on_source_type_changed()

    def _populate_monitors(self) -> None:
        current = self._manager.settings.capture.monitor_index
        self._monitor_combo.clear()
        monitors = available_monitors()
        if not monitors:
            # No mss / headless: let the operator still type an index via fallbacks.
            for index in range(1, 5):
                self._monitor_combo.addItem(f"Monitor {index}", index)
        else:
            for info in monitors:
                self._monitor_combo.addItem(info.label, info.index)
        pick = self._monitor_combo.findData(current)
        if pick >= 0:
            self._monitor_combo.setCurrentIndex(pick)

    def _selected_source_type(self) -> CaptureSourceType:
        return CaptureSourceType(self._source_combo.currentData())

    def _on_source_type_changed(self) -> None:
        is_monitor = self._selected_source_type() is CaptureSourceType.MONITOR
        self._monitor_row_widget.setEnabled(is_monitor)

    # -- button handlers -------------------------------------------------- #
    def _on_apply_source(self) -> None:
        settings = self._manager.settings.model_copy(deep=True)
        settings.capture.source = self._selected_source_type()
        if self._monitor_combo.currentData() is not None:
            settings.capture.monitor_index = int(self._monitor_combo.currentData())
        self._manager.update(settings, section="capture")
        try:
            self._pipeline.set_source(create_frame_source(self._manager.settings.capture))
        except Exception as exc:  # noqa: BLE001 - report source build/open failures
            QMessageBox.critical(self, "Capture error", f"Could not switch source:\n{exc}")
            return
        self._source.setText(self._pipeline.source.name)
        QMessageBox.information(
            self,
            "Source updated",
            "Capture source saved. Click “Refresh preview” to see it, or “Start capture”.",
        )

    def _on_snapshot(self) -> None:
        try:
            self._pipeline.snapshot()
        except Exception as exc:  # noqa: BLE001 - grabbing may fail if the source can't open
            QMessageBox.warning(self, "Preview failed", f"Could not grab a frame:\n{exc}")
            return
        if not self._render_preview():
            self._preview.setText("No frame available from this source yet.")

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
        # Source can't be swapped mid-capture without a restart, so lock it while live.
        self._apply_btn.setEnabled(not running)
        self._source_combo.setEnabled(not running)
        self._monitor_row_widget.setEnabled(
            not running and self._selected_source_type() is CaptureSourceType.MONITOR
        )
        self._source.setText(source)

    def on_capture_stats(self, stats: CaptureStats) -> None:
        if stats is None:
            return
        self._fps.setText(f"{stats.actual_fps:.1f} / {stats.target_fps:.0f}")
        self._frames.setText(str(stats.frames_captured))
        self._dropped.setText(f"{stats.frames_dropped}  ({stats.drop_rate * 100:.1f}%)")
        self._latency.setText(f"{stats.avg_capture_ms:.2f} ms")
        self._render_preview()

    def _render_preview(self) -> bool:
        frame = self._pipeline.latest_frame()
        if frame is None or not frame.is_valid:
            return False
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
        return True
