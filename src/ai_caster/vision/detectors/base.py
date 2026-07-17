"""The detector interface.

A detector is a pure function of pixels: it takes an image (an ``H x W x 3``
uint8 BGR array — already downscaled by the pipeline) plus the source frame
index, and returns zero or more confidence-scored observations. Purity is what
makes every detector trivially unit-testable with a hand-crafted array.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ai_caster.vision.observations import VisionObservation


def clamp01(value: float) -> float:
    """Clamp to ``[0, 1]``."""
    return max(0.0, min(1.0, float(value)))


def confidence_from_range(value: float, lo: float, hi: float) -> float:
    """Map ``value`` in ``[lo, hi]`` linearly to a confidence in ``[0, 1]``."""
    if hi <= lo:
        return 0.0
    return clamp01((value - lo) / (hi - lo))


class VisionDetector(ABC):
    """Base class for all vision detectors."""

    #: Stable identifier used in logs, settings toggles and the UI.
    name: str = "detector"

    @abstractmethod
    def detect(self, image: np.ndarray, frame_index: int) -> list[VisionObservation]:
        """Return observations for one frame (possibly empty)."""
        raise NotImplementedError
