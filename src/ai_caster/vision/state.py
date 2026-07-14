"""The consolidated vision state for a frame.

A frame's observations are folded into a single immutable :class:`VisionState`
that the UI, the match model annotation and the future Commentary Director read.
Each effect cue keeps both an ``active`` flag (thresholded at the pipeline's
minimum confidence) and the raw confidence, so downstream code can be as strict
or as lenient as it needs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ai_caster.vision.observations import ObservationKind, SceneType, VisionObservation


@dataclass(frozen=True)
class Cue:
    """A boolean cue with the confidence behind it."""

    active: bool = False
    confidence: float = 0.0


@dataclass(frozen=True)
class VisionState:
    """Immutable summary of what vision saw in one frame."""

    frame_index: int = -1
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    scene: SceneType = SceneType.UNKNOWN
    scene_confidence: float = 0.0
    flash: Cue = field(default_factory=Cue)
    smoke: Cue = field(default_factory=Cue)
    fire: Cue = field(default_factory=Cue)
    hud: Cue = field(default_factory=Cue)
    kill_feed: Cue = field(default_factory=Cue)
    bomb_timer: Cue = field(default_factory=Cue)
    observations: tuple[VisionObservation, ...] = ()

    @classmethod
    def from_observations(
        cls,
        frame_index: int,
        observations: Iterable[VisionObservation],
        *,
        min_confidence: float,
    ) -> VisionState:
        obs = list(observations)
        by_kind: dict[ObservationKind, VisionObservation] = {}
        for observation in obs:
            current = by_kind.get(observation.kind)
            if current is None or observation.confidence > current.confidence:
                by_kind[observation.kind] = observation

        def cue(kind: ObservationKind) -> Cue:
            found = by_kind.get(kind)
            if found is None:
                return Cue()
            return Cue(active=found.confidence >= min_confidence, confidence=found.confidence)

        scene_obs = by_kind.get(ObservationKind.SCENE)
        scene = SceneType(scene_obs.value) if scene_obs and scene_obs.value else SceneType.UNKNOWN
        scene_confidence = scene_obs.confidence if scene_obs else 0.0

        return cls(
            frame_index=frame_index,
            scene=scene,
            scene_confidence=scene_confidence,
            flash=cue(ObservationKind.FLASH),
            smoke=cue(ObservationKind.SMOKE),
            fire=cue(ObservationKind.FIRE),
            hud=cue(ObservationKind.HUD_VISIBLE),
            kill_feed=cue(ObservationKind.KILL_FEED_ACTIVITY),
            bomb_timer=cue(ObservationKind.BOMB_TIMER_VISIBLE),
            observations=tuple(obs),
        )
