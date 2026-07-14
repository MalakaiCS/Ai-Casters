"""Vision observation types.

A :class:`VisionObservation` is one confidence-scored thing a detector saw in a
frame. Confidence is always in ``[0, 1]`` and is honest: analytic heuristics
report modest confidences, and the fusion layer only lets vision inform the match
model where GSI is silent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ObservationKind(StrEnum):
    FLASH = "flash"
    SMOKE = "smoke"
    FIRE = "fire"
    KILL_FEED_ACTIVITY = "kill_feed_activity"
    BOMB_TIMER_VISIBLE = "bomb_timer_visible"
    HUD_VISIBLE = "hud_visible"
    SCENE = "scene"
    OBJECT = "object"  # produced by the ONNX object detector


class SceneType(StrEnum):
    """Coarse camera/scene classification of a frame."""

    LIVE = "live"
    REPLAY = "replay"
    PLAYER_CAMERA = "player_camera"
    CROWD_CAMERA = "crowd_camera"
    MAP_OVERVIEW = "map_overview"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VisionObservation:
    """One confidence-scored detection in a single frame."""

    kind: ObservationKind
    confidence: float
    frame_index: int
    region: str | None = None
    value: Any = None
    detail: dict[str, Any] = field(default_factory=dict)
