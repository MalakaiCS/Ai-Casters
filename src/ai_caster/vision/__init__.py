"""Module 7 — Computer Vision.

Watches the captured observer feed and produces confidence-scored observations —
flash/smoke/molotov effects, kill-feed and bomb-timer activity, HUD presence and
scene/camera classification. These are fused into the Match Engine under the
project's priority of truth (**Server > GSI > Vision > Inference**), so uncertain
vision never overrides confirmed match data.

Two detector families share one interface:
- **Analytic** detectors (classical CV in NumPy) — no model, always available,
  fully unit-tested. Good for effects and coarse cues.
- **Model-backed** detector (ONNX) — optional, loads user-supplied weights for
  production-grade object detection (kill-feed OCR, icons, precise HUD reads).
"""

from ai_caster.vision.observations import (
    ObservationKind,
    SceneType,
    VisionObservation,
)
from ai_caster.vision.pipeline import VisionPipeline
from ai_caster.vision.state import VisionState

__all__ = [
    "VisionPipeline",
    "VisionState",
    "VisionObservation",
    "ObservationKind",
    "SceneType",
]
