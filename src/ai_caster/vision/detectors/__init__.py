"""Vision detectors — one interface, two families (analytic and model-backed)."""

from ai_caster.vision.detectors.base import VisionDetector, clamp01
from ai_caster.vision.detectors.effects import FireDetector, FlashDetector, SmokeDetector
from ai_caster.vision.detectors.hud import (
    BombTimerDetector,
    HudPresenceDetector,
    KillFeedActivityDetector,
)
from ai_caster.vision.detectors.scene import SceneClassifier

__all__ = [
    "VisionDetector",
    "clamp01",
    "FlashDetector",
    "SmokeDetector",
    "FireDetector",
    "KillFeedActivityDetector",
    "BombTimerDetector",
    "HudPresenceDetector",
    "SceneClassifier",
]
