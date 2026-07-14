"""Computer Vision view.

Enables/disables the vision pipeline and shows the latest confidence-scored
observations: scene/camera classification, effect cues (flash/smoke/fire), HUD
and kill-feed activity, plus the active detectors. Updates arrive on the Qt
thread via the event bridge.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ai_caster.vision.pipeline import VisionPipeline
from ai_caster.vision.state import Cue, VisionState


class VisionView(QWidget):
    """Controls vision and displays its confidence-scored observations."""

    def __init__(self, pipeline: VisionPipeline) -> None:
        super().__init__()
        self._pipeline = pipeline

        root = QVBoxLayout(self)
        title = QLabel("Computer Vision")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        self._enable = QCheckBox("Enable vision analysis (requires capture running)")
        self._enable.setChecked(pipeline.enabled)
        self._enable.toggled.connect(self._pipeline.set_enabled)
        root.addWidget(self._enable)

        detectors = QLabel("Detectors: " + ", ".join(pipeline.detector_names))
        detectors.setStyleSheet("color: #888;")
        detectors.setWordWrap(True)
        root.addWidget(detectors)

        # Scene.
        scene_box = QGroupBox("Scene / camera")
        scene_form = QFormLayout(scene_box)
        self._scene = QLabel("—")
        self._scene_conf = QProgressBar()
        self._scene_conf.setRange(0, 100)
        scene_form.addRow("Classification:", self._scene)
        scene_form.addRow("Confidence:", self._scene_conf)
        root.addWidget(scene_box)

        # Effect / activity cues.
        cues_box = QGroupBox("Cues (confidence %)")
        cues_form = QFormLayout(cues_box)
        self._bars: dict[str, QProgressBar] = {}
        for label in ("Flash", "Smoke", "Fire", "HUD", "Kill feed", "Bomb timer"):
            bar = QProgressBar()
            bar.setRange(0, 100)
            self._bars[label] = bar
            cues_form.addRow(f"{label}:", bar)
        root.addWidget(cues_box)

        self._processed = QLabel("0 frames analysed")
        self._processed.setStyleSheet("color: #888;")
        root.addWidget(self._processed)
        root.addStretch(1)

    # -- slot (Qt thread) ------------------------------------------------ #
    def on_vision_state(self, state: VisionState) -> None:
        if state is None:
            return
        self._scene.setText(f"{state.scene.value}")
        self._scene_conf.setValue(int(state.scene_confidence * 100))

        def pct(cue: Cue) -> int:
            return int(cue.confidence * 100)

        self._bars["Flash"].setValue(pct(state.flash))
        self._bars["Smoke"].setValue(pct(state.smoke))
        self._bars["Fire"].setValue(pct(state.fire))
        self._bars["HUD"].setValue(pct(state.hud))
        self._bars["Kill feed"].setValue(pct(state.kill_feed))
        self._bars["Bomb timer"].setValue(pct(state.bomb_timer))
        self._processed.setText(f"{self._pipeline.processed_count} frames analysed")
