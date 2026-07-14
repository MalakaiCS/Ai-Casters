"""Tests for the on-screen replay-banner detector and its fusion."""

from __future__ import annotations

import numpy as np

from ai_caster.vision import roi
from ai_caster.vision.detectors.replay import ReplayTextDetector
from ai_caster.vision.observations import ObservationKind, SceneType
from ai_caster.vision.state import VisionState

W, H = 640, 360


def _frame() -> np.ndarray:
    return np.zeros((H, W, 3), dtype=np.uint8)


def _fill(frame: np.ndarray, region: roi.Region, value: int) -> None:
    x0, y0, x1, y1 = region.pixels(W, H)
    frame[y0:y1, x0:x1] = value


def _banner(frame: np.ndarray, region: roi.Region) -> None:
    """Paint a dark banner with white vertical 'text' strokes in the region."""
    x0, y0, x1, y1 = region.pixels(W, H)
    frame[y0:y1, x0:x1] = 30  # dark, uniform banner background
    # White vertical strokes -> crisp high-contrast edges (text-like).
    for x in range(x0 + 2, x1 - 1, 6):
        frame[y0:y1, x : x + 2] = 240


def test_detects_banner_region():
    frame = _frame()
    _banner(frame, roi.REPLAY_BANNER)
    hits = ReplayTextDetector().detect(frame, 0)
    assert len(hits) == 1
    assert hits[0].kind is ObservationKind.SCENE
    assert hits[0].value == SceneType.REPLAY.value
    assert hits[0].confidence > 0.3


def test_flat_region_is_not_replay():
    frame = _frame()
    _fill(frame, roi.REPLAY_BANNER, 30)  # uniform, no text edges
    assert ReplayTextDetector().detect(frame, 0) == []


def test_busy_noise_region_is_not_replay():
    rng = np.random.default_rng(0)
    frame = _frame()
    x0, y0, x1, y1 = roi.REPLAY_BANNER.pixels(W, H)
    frame[y0:y1, x0:x1] = rng.integers(0, 256, size=(y1 - y0, x1 - x0, 3), dtype=np.uint8)
    # Random noise has no dominant background -> rejected.
    assert ReplayTextDetector().detect(frame, 0) == []


def test_vision_state_scene_becomes_replay_when_banner_wins():
    frame = _frame()
    _banner(frame, roi.REPLAY_BANNER)
    from ai_caster.vision.detectors.scene import SceneClassifier

    observations = ReplayTextDetector().detect(frame, 0) + SceneClassifier().detect(frame, 0)
    state = VisionState.from_observations(0, observations, min_confidence=0.6)
    assert state.scene is SceneType.REPLAY
