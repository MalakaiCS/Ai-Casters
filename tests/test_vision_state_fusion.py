"""Tests for VisionState assembly and priority-of-truth fusion."""

from __future__ import annotations

from ai_caster.match.state import DataSource
from ai_caster.vision.fusion import Signal, fuse, fuse_effect
from ai_caster.vision.observations import ObservationKind, SceneType, VisionObservation
from ai_caster.vision.state import VisionState


def _obs(kind: ObservationKind, confidence: float, value=None) -> VisionObservation:
    return VisionObservation(kind=kind, confidence=confidence, frame_index=0, value=value)


def test_vision_state_from_observations_thresholds_cues():
    observations = [
        _obs(ObservationKind.FLASH, 0.9),
        _obs(ObservationKind.SMOKE, 0.3),  # below min_confidence -> inactive
        _obs(ObservationKind.SCENE, 0.6, SceneType.LIVE.value),
    ]
    state = VisionState.from_observations(5, observations, min_confidence=0.6)
    assert state.frame_index == 5
    assert state.flash.active is True and state.flash.confidence == 0.9
    assert state.smoke.active is False and state.smoke.confidence == 0.3
    assert state.scene is SceneType.LIVE
    assert state.scene_confidence == 0.6


def test_vision_state_keeps_highest_confidence_per_kind():
    observations = [
        _obs(ObservationKind.FIRE, 0.4),
        _obs(ObservationKind.FIRE, 0.8),
    ]
    state = VisionState.from_observations(0, observations, min_confidence=0.6)
    assert state.fire.confidence == 0.8
    assert state.fire.active is True


def test_fuse_prefers_higher_priority_source():
    gsi = Signal("gsi", DataSource.GSI, 0.5)
    vision = Signal("vision", DataSource.VISION, 0.99)
    assert fuse([vision, gsi]).value == "gsi"  # GSI outranks vision even at lower confidence


def test_fuse_breaks_ties_by_confidence():
    a = Signal("a", DataSource.VISION, 0.4)
    b = Signal("b", DataSource.VISION, 0.7)
    assert fuse([a, b]).value == "b"


def test_fuse_ignores_none_and_empty():
    assert fuse([None, None]) is None
    assert fuse([]) is None


def test_fuse_effect_gsi_always_wins():
    # GSI says not flashed; vision (confidently) says flashed -> GSI wins.
    value, source = fuse_effect(gsi_value=False, vision_active=True, vision_confidence=0.95)
    assert value is False
    assert source is DataSource.GSI


def test_fuse_effect_uses_vision_when_gsi_silent():
    value, source = fuse_effect(gsi_value=None, vision_active=True, vision_confidence=0.8)
    assert value is True
    assert source is DataSource.VISION


def test_fuse_effect_defaults_to_false():
    value, source = fuse_effect(gsi_value=None, vision_active=False, vision_confidence=0.0)
    assert value is False
    assert source is DataSource.INFERENCE
