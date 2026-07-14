"""Tests for the analytic vision detectors, on hand-crafted frames."""

from __future__ import annotations

import numpy as np

from ai_caster.vision import roi
from ai_caster.vision.detectors import (
    BombTimerDetector,
    FireDetector,
    FlashDetector,
    HudPresenceDetector,
    KillFeedActivityDetector,
    SceneClassifier,
    SmokeDetector,
)
from ai_caster.vision.observations import ObservationKind, SceneType

W, H = 640, 360


def solid(b: int, g: int, r: int) -> np.ndarray:
    frame = np.empty((H, W, 3), dtype=np.uint8)
    frame[:, :, 0] = b
    frame[:, :, 1] = g
    frame[:, :, 2] = r
    return frame


def fill_region(frame: np.ndarray, region: roi.Region, b: int, g: int, r: int) -> None:
    x0, y0, x1, y1 = region.pixels(W, H)
    frame[y0:y1, x0:x1] = (b, g, r)


def test_flash_fires_on_white_and_not_on_gray():
    flash = FlashDetector()
    hits = flash.detect(solid(255, 255, 255), 0)
    assert len(hits) == 1
    assert hits[0].kind == ObservationKind.FLASH
    assert hits[0].confidence > 0.8
    assert flash.detect(solid(100, 100, 100), 1) == []


def test_smoke_fires_on_midtone_gray():
    hits = SmokeDetector().detect(solid(128, 128, 128), 0)
    assert len(hits) == 1
    assert hits[0].kind == ObservationKind.SMOKE
    assert hits[0].confidence > 0.5


def test_fire_fires_on_orange():
    hits = FireDetector().detect(solid(20, 120, 240), 0)
    assert len(hits) == 1
    assert hits[0].kind == ObservationKind.FIRE
    assert SmokeDetector().detect(solid(20, 120, 240), 0) == []  # orange is not smoke


def test_kill_feed_activity_on_team_colours():
    frame = solid(0, 0, 0)
    fill_region(frame, roi.KILL_FEED, 220, 60, 20)  # CT blue
    hits = KillFeedActivityDetector().detect(frame, 0)
    assert hits and hits[0].kind == ObservationKind.KILL_FEED_ACTIVITY


def test_bomb_timer_on_red_region():
    frame = solid(0, 0, 0)
    fill_region(frame, roi.BOMB_TIMER, 0, 0, 255)  # red
    hits = BombTimerDetector().detect(frame, 0)
    assert hits and hits[0].kind == ObservationKind.BOMB_TIMER_VISIBLE


def test_hud_presence_contrast():
    detector = HudPresenceDetector()
    # Flat frame -> low/zero confidence but still reports the cue.
    flat = detector.detect(solid(0, 0, 0), 0)
    assert flat and flat[0].kind == ObservationKind.HUD_VISIBLE
    assert flat[0].confidence == 0.0

    # High-contrast HUD band -> strong confidence.
    frame = solid(0, 0, 0)
    x0, y0, x1, y1 = roi.HUD_BOTTOM.pixels(W, H)
    gradient = np.linspace(0, 255, x1 - x0).astype(np.uint8)
    frame[y0:y1, x0:x1, :] = gradient[None, :, None]
    hud = detector.detect(frame, 1)
    assert hud[0].confidence > 0.5


def test_scene_live_when_hud_present():
    frame = solid(0, 0, 0)
    x0, y0, x1, y1 = roi.HUD_BOTTOM.pixels(W, H)
    gradient = np.linspace(0, 255, x1 - x0).astype(np.uint8)
    frame[y0:y1, x0:x1, :] = gradient[None, :, None]
    obs = SceneClassifier().detect(frame, 0)[0]
    assert obs.value == SceneType.LIVE.value
    assert obs.confidence >= 0.35


def test_scene_crowd_when_colourful_without_hud():
    frame = solid(0, 0, 0)
    fill_region(frame, roi.PLAY_AREA, 255, 0, 255)  # bright saturated magenta
    obs = SceneClassifier().detect(frame, 0)[0]
    assert obs.value == SceneType.CROWD_CAMERA.value


def test_scene_unknown_when_dark_and_flat():
    obs = SceneClassifier().detect(solid(0, 0, 0), 0)[0]
    assert obs.value == SceneType.UNKNOWN.value
