"""Effect detectors: flashbang, smoke and molotov/fire.

These use classical colour statistics (see :mod:`ai_caster.vision.color`) rather
than a model, so they are always available and fully testable. They corroborate
GSI (which already reports per-player flashed/smoked/burning) and add a
screen-space intensity GSI does not provide; per the priority of truth, GSI
remains authoritative and these only inform where GSI is silent.
"""

from __future__ import annotations

import numpy as np

from ai_caster.vision import color, roi
from ai_caster.vision.detectors.base import VisionDetector, confidence_from_range
from ai_caster.vision.observations import ObservationKind, VisionObservation


class FlashDetector(VisionDetector):
    """Detects a flashbang wash-out from near-white, desaturated full frames."""

    name = "flash"

    def __init__(self, low: float = 0.5, high: float = 0.9) -> None:
        self._low = low
        self._high = high

    def detect(self, image: np.ndarray, frame_index: int) -> list[VisionObservation]:
        fraction = color.white_fraction(image)
        confidence = confidence_from_range(fraction, self._low, self._high)
        if confidence <= 0.0:
            return []
        return [
            VisionObservation(
                kind=ObservationKind.FLASH,
                confidence=confidence,
                frame_index=frame_index,
                region=roi.FULL.name,
                value=round(fraction, 4),
                detail={"white_fraction": round(fraction, 4)},
            )
        ]


class SmokeDetector(VisionDetector):
    """Detects smoke from large mid-tone, low-saturation areas in the play area."""

    name = "smoke"

    def __init__(self, low: float = 0.20, high: float = 0.55) -> None:
        self._low = low
        self._high = high

    def detect(self, image: np.ndarray, frame_index: int) -> list[VisionObservation]:
        region = roi.PLAY_AREA.crop(image)
        fraction = color.gray_fraction(region)
        confidence = confidence_from_range(fraction, self._low, self._high)
        if confidence <= 0.0:
            return []
        return [
            VisionObservation(
                kind=ObservationKind.SMOKE,
                confidence=confidence,
                frame_index=frame_index,
                region=roi.PLAY_AREA.name,
                value=round(fraction, 4),
                detail={"gray_fraction": round(fraction, 4)},
            )
        ]


class FireDetector(VisionDetector):
    """Detects molotov/incendiary fire from saturated orange in the play area."""

    name = "fire"

    def __init__(self, low: float = 0.02, high: float = 0.20) -> None:
        self._low = low
        self._high = high

    def detect(self, image: np.ndarray, frame_index: int) -> list[VisionObservation]:
        region = roi.PLAY_AREA.crop(image)
        fraction = color.orange_fraction(region)
        confidence = confidence_from_range(fraction, self._low, self._high)
        if confidence <= 0.0:
            return []
        return [
            VisionObservation(
                kind=ObservationKind.FIRE,
                confidence=confidence,
                frame_index=frame_index,
                region=roi.PLAY_AREA.name,
                value=round(fraction, 4),
                detail={"orange_fraction": round(fraction, 4)},
            )
        ]
