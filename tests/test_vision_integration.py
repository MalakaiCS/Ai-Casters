"""Vision <-> Match Engine integration: annotation without override."""

from __future__ import annotations

from ai_caster.core.events import EventBus, GSIStateUpdated
from ai_caster.gsi.models import GameState
from ai_caster.match.engine import MatchStateEngine
from ai_caster.statistics.engine import StatisticsEngine
from ai_caster.vision.events import VisionStateUpdated
from ai_caster.vision.observations import ObservationKind, SceneType, VisionObservation
from ai_caster.vision.state import VisionState
from tests.conftest import make_player, make_state


def _vision_state(scene: SceneType) -> VisionState:
    return VisionState.from_observations(
        3,
        [VisionObservation(ObservationKind.SCENE, 0.6, 3, value=scene.value)],
        min_confidence=0.5,
    )


def test_vision_state_annotates_match_model():
    bus = EventBus()
    engine = MatchStateEngine(bus, StatisticsEngine(), persist=False)

    # Vision arrives first, then a GSI update builds the model.
    bus.publish(VisionStateUpdated(state=_vision_state(SceneType.LIVE)))
    bus.publish(
        GSIStateUpdated(
            game_state=GameState.model_validate(make_state([make_player("1", "a", "CT")]))
        )
    )

    live = engine.live_match
    assert live is not None
    assert live.visual is not None
    assert live.visual.scene is SceneType.LIVE
    engine.dispose()


def test_model_builds_without_vision():
    bus = EventBus()
    engine = MatchStateEngine(bus, StatisticsEngine(), persist=False)
    bus.publish(
        GSIStateUpdated(
            game_state=GameState.model_validate(make_state([make_player("1", "a", "CT")]))
        )
    )
    assert engine.live_match.visual is None  # no vision yet -> plain model
    engine.dispose()
