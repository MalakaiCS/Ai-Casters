"""On-screen replay-banner detector.

Broadcasts overlay a "REPLAY" text banner while showing replay footage. That
banner is a strong, reliable visual cue, so — unlike the general scene classifier
— this detector *can* assert ``SCENE=REPLAY`` with real confidence.

It looks in a configurable region for the signature of a text banner: crisp,
high-contrast edges (the glyphs) sitting on a fairly uniform background (the
overlay). It does not read the word itself — the optional ONNX detector is the
path to precise text/OCR — but banner presence in the replay-indicator region is
enough to flag replay.

Priority of truth is preserved: this is still *vision*. The external replay
integration (M5) remains authoritative and outranks this hint; the Commentary
Director only consults the vision signal when replay integration is unavailable.
"""

from __future__ import annotations

import numpy as np

from ai_caster.vision import color, roi
from ai_caster.vision.detectors.base import VisionDetector, confidence_from_range
from ai_caster.vision.observations import ObservationKind, SceneType, VisionObservation


class ReplayTextDetector(VisionDetector):
    """Detects the on-screen replay banner and reports ``SCENE=REPLAY``."""

    name = "replay_text"

    def __init__(
        self,
        region: roi.Region = roi.REPLAY_BANNER,
        *,
        edge_low: float = 0.02,
        edge_high: float = 0.12,
        background_min: float = 0.35,
        max_confidence: float = 0.85,
    ) -> None:
        self._region = region
        self._edge_low = edge_low
        self._edge_high = edge_high
        self._background_min = background_min
        self._max_confidence = max_confidence

    def detect(self, image: np.ndarray, frame_index: int) -> list[VisionObservation]:
        crop = self._region.crop(image)
        edges = color.edge_fraction(crop)
        background = color.background_dominance(crop)

        # Require both a text-like edge signature and a dominant banner background
        # so busy gameplay in the region doesn't trigger a false replay.
        if edges < self._edge_low or background < self._background_min:
            return []

        confidence = confidence_from_range(edges, self._edge_low, self._edge_high)
        confidence = min(confidence, self._max_confidence)
        if confidence <= 0.0:
            return []
        return [
            VisionObservation(
                kind=ObservationKind.SCENE,
                confidence=confidence,
                frame_index=frame_index,
                region=self._region.name,
                value=SceneType.REPLAY.value,
                detail={"edge_fraction": round(edges, 4), "background": round(background, 4)},
            )
        ]
