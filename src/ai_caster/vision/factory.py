"""Build the detector list and the vision pipeline from settings.

Keeps the composition root declarative: toggles in :class:`VisionSettings` decide
which analytic detectors run, and a configured ``model_path`` adds the optional
ONNX object detector (loaded eagerly here so a bad path fails at startup, not
mid-broadcast).
"""

from __future__ import annotations

from ai_caster.config.models import VisionSettings
from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger
from ai_caster.vision.detectors import (
    BombTimerDetector,
    FireDetector,
    FlashDetector,
    HudPresenceDetector,
    KillFeedActivityDetector,
    SceneClassifier,
    SmokeDetector,
    VisionDetector,
)
from ai_caster.vision.pipeline import VisionPipeline

_log = get_logger("vision.factory")


def build_detectors(settings: VisionSettings) -> list[VisionDetector]:
    """Assemble the enabled detectors for the given settings."""
    detectors: list[VisionDetector] = []
    if settings.detect_flash:
        detectors.append(FlashDetector())
    if settings.detect_smoke:
        detectors.append(SmokeDetector())
    if settings.detect_fire:
        detectors.append(FireDetector())
    if settings.detect_kill_feed:
        detectors.append(KillFeedActivityDetector())
    if settings.detect_bomb_timer:
        detectors.append(BombTimerDetector())
    if settings.detect_hud:
        detectors.append(HudPresenceDetector())
    if settings.detect_scene:
        detectors.append(SceneClassifier())

    if settings.model_path:
        from ai_caster.vision.detectors.onnx_detector import OnnxObjectDetector

        onnx = OnnxObjectDetector(
            settings.model_path,
            score_threshold=settings.min_confidence,
            use_gpu=settings.use_gpu,
        )
        try:
            onnx.load()
            detectors.append(onnx)
        except RuntimeError as exc:
            # Don't take the whole app down for a bad model path; log and run the
            # analytic detectors only.
            _log.warning("ONNX detector unavailable (%s); using analytic detectors only.", exc)

    return detectors


def create_vision_pipeline(settings: VisionSettings, event_bus: EventBus) -> VisionPipeline:
    """Construct the vision pipeline described by ``settings``."""
    return VisionPipeline(
        build_detectors(settings),
        event_bus,
        min_confidence=settings.min_confidence,
        process_fps=settings.process_fps,
        downscale_width=settings.downscale_width,
        enabled=settings.enabled,
    )
