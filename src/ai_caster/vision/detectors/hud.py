"""HUD-region detectors: kill-feed activity, bomb-timer visibility, HUD presence.

These are ROI *activity* heuristics, not readers: they report that a region has
the colour/structure signature of the thing (coloured kill-feed rows, a red bomb
timer, a structured HUD bar) with a modest confidence. Reading names, weapons and
exact timers is the ONNX detector's job (M7 model-backed path); these keep the
system useful without a model and give the vision fusion a coarse signal.
"""

from __future__ import annotations

import numpy as np

from ai_caster.vision import color, roi
from ai_caster.vision.detectors.base import VisionDetector, clamp01, confidence_from_range
from ai_caster.vision.observations import ObservationKind, VisionObservation


def _team_colored_fraction(bgr: np.ndarray) -> float:
    """Fraction of pixels that are saturated CT-blue or T-yellow/orange.

    Kill-feed rows and team text carry these colours, so their presence in the
    kill-feed region indicates recent activity.
    """
    arr = bgr.astype(np.float32) / 255.0
    b, g, r = arr[..., 0], arr[..., 1], arr[..., 2]
    sat = color.saturation_map(bgr)
    ct_blue = (b > 0.45) & (b - r > 0.15) & (sat > 0.30)
    t_yellow = (r > 0.45) & (g > 0.35) & (b < 0.40) & (sat > 0.30)
    return float((ct_blue | t_yellow).mean())


class KillFeedActivityDetector(VisionDetector):
    """Flags coloured activity in the top-right kill-feed region."""

    name = "kill_feed"

    def __init__(self, low: float = 0.01, high: float = 0.12) -> None:
        self._low = low
        self._high = high

    def detect(self, image: np.ndarray, frame_index: int) -> list[VisionObservation]:
        region = roi.KILL_FEED.crop(image)
        fraction = _team_colored_fraction(region)
        confidence = confidence_from_range(fraction, self._low, self._high)
        if confidence <= 0.0:
            return []
        return [
            VisionObservation(
                kind=ObservationKind.KILL_FEED_ACTIVITY,
                confidence=confidence,
                frame_index=frame_index,
                region=roi.KILL_FEED.name,
                value=round(fraction, 4),
            )
        ]


class BombTimerDetector(VisionDetector):
    """Flags a visible (red) bomb timer in its HUD region."""

    name = "bomb_timer"

    def __init__(self, low: float = 0.05, high: float = 0.35) -> None:
        self._low = low
        self._high = high

    def detect(self, image: np.ndarray, frame_index: int) -> list[VisionObservation]:
        region = roi.BOMB_TIMER.crop(image)
        arr = region.astype(np.float32) / 255.0
        b, g, r = arr[..., 0], arr[..., 1], arr[..., 2]
        red = (r > 0.55) & (r - g > 0.25) & (r - b > 0.25)
        fraction = float(red.mean())
        confidence = confidence_from_range(fraction, self._low, self._high)
        if confidence <= 0.0:
            return []
        return [
            VisionObservation(
                kind=ObservationKind.BOMB_TIMER_VISIBLE,
                confidence=confidence,
                frame_index=frame_index,
                region=roi.BOMB_TIMER.name,
                value=round(fraction, 4),
            )
        ]


class HudPresenceDetector(VisionDetector):
    """Estimates whether the gameplay HUD is on screen.

    The bottom HUD bar is structured and moderately bright, giving the region a
    high local contrast (luma standard deviation). A blank/crowd/replay frame in
    that band is comparatively flat.
    """

    name = "hud"

    def __init__(self, low: float = 0.06, high: float = 0.22) -> None:
        self._low = low
        self._high = high

    def detect(self, image: np.ndarray, frame_index: int) -> list[VisionObservation]:
        region = roi.HUD_BOTTOM.crop(image).astype(np.float32) / 255.0
        luma = 0.114 * region[..., 0] + 0.587 * region[..., 1] + 0.299 * region[..., 2]
        contrast = float(luma.std())
        confidence = confidence_from_range(contrast, self._low, self._high)
        # Always report HUD presence (0..1) so the scene classifier can consume it.
        return [
            VisionObservation(
                kind=ObservationKind.HUD_VISIBLE,
                confidence=clamp01(confidence),
                frame_index=frame_index,
                region=roi.HUD_BOTTOM.name,
                value=round(contrast, 4),
            )
        ]
