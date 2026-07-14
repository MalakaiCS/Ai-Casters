"""Tests for regions of interest."""

from __future__ import annotations

import numpy as np

from ai_caster.vision import roi


def test_region_pixels_scale_with_resolution():
    region = roi.Region("r", 0.5, 0.5, 0.5, 0.5)
    assert region.pixels(1000, 1000) == (500, 500, 1000, 1000)
    assert region.pixels(1920, 1080) == (960, 540, 1920, 1080)


def test_region_pixels_clamped():
    region = roi.Region("r", 0.9, 0.9, 0.5, 0.5)  # extends past the edge
    x0, y0, x1, y1 = region.pixels(100, 100)
    assert x1 == 100 and y1 == 100
    assert x0 < x1 and y0 < y1


def test_region_crop_shape():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    crop = roi.KILL_FEED.crop(frame)
    assert crop.ndim == 3
    assert crop.shape[2] == 3
    assert crop.shape[0] > 0 and crop.shape[1] > 0


def test_full_region_is_whole_frame():
    frame = np.zeros((50, 80, 3), dtype=np.uint8)
    assert roi.FULL.crop(frame).shape == frame.shape


def test_default_regions_registered():
    for name in ("full", "kill_feed", "scoreboard", "bomb_timer", "hud_bottom", "play_area"):
        assert name in roi.DEFAULT_REGIONS
