"""Heuristic scene / camera classifier.

Classifies a frame as live gameplay, a crowd camera, or unknown, from HUD
contrast and play-area colour statistics. This is an honest heuristic with
**capped confidence** — robust camera classification (player vs. crowd vs. map
overview) is the trained model's job, and authoritative *replay* state comes from
the external replay integration (M5), never from guessing at pixels. So this
classifier never emits a high-confidence ``REPLAY``; it sticks to what pixels can
support and defers otherwise.
"""

from __future__ import annotations

import numpy as np

from ai_caster.vision import color, roi
from ai_caster.vision.detectors.base import VisionDetector, clamp01
from ai_caster.vision.observations import ObservationKind, SceneType, VisionObservation

_MAX_HEURISTIC_CONFIDENCE = 0.7


class SceneClassifier(VisionDetector):
    """Coarse camera/scene classification."""

    name = "scene"

    def __init__(self, hud_threshold: float = 0.12) -> None:
        self._hud_threshold = hud_threshold

    def detect(self, image: np.ndarray, frame_index: int) -> list[VisionObservation]:
        hud = roi.HUD_BOTTOM.crop(image).astype(np.float32) / 255.0
        hud_luma = 0.114 * hud[..., 0] + 0.587 * hud[..., 1] + 0.299 * hud[..., 2]
        hud_contrast = float(hud_luma.std())

        play = roi.PLAY_AREA.crop(image)
        play_sat = color.mean_saturation(play)
        play_bright = color.brightness(play)

        scene, confidence = self._classify(hud_contrast, play_sat, play_bright)
        return [
            VisionObservation(
                kind=ObservationKind.SCENE,
                confidence=confidence,
                frame_index=frame_index,
                region=roi.FULL.name,
                value=scene.value,
                detail={
                    "hud_contrast": round(hud_contrast, 4),
                    "play_saturation": round(play_sat, 4),
                    "play_brightness": round(play_bright, 4),
                },
            )
        ]

    def _classify(
        self, hud_contrast: float, play_sat: float, play_bright: float
    ) -> tuple[SceneType, float]:
        if hud_contrast >= self._hud_threshold:
            # HUD present -> in-game observer camera.
            confidence = (
                clamp01(hud_contrast / (self._hud_threshold * 2)) * _MAX_HEURISTIC_CONFIDENCE
            )
            return SceneType.LIVE, max(0.35, confidence)
        # No HUD: a colourful, bright frame looks like a crowd shot; otherwise defer.
        if play_sat > 0.25 and play_bright > 0.3:
            return SceneType.CROWD_CAMERA, 0.4
        return SceneType.UNKNOWN, 0.25
