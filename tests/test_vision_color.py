"""Tests for the NumPy colour-statistics helpers."""

from __future__ import annotations

import numpy as np

from ai_caster.vision import color


def _solid(b: int, g: int, r: int, size: int = 8) -> np.ndarray:
    frame = np.empty((size, size, 3), dtype=np.uint8)
    frame[:, :, 0] = b
    frame[:, :, 1] = g
    frame[:, :, 2] = r
    return frame


def test_brightness_white_and_black():
    assert color.brightness(_solid(255, 255, 255)) == 1.0
    assert color.brightness(_solid(0, 0, 0)) == 0.0


def test_white_fraction_detects_white():
    assert color.white_fraction(_solid(255, 255, 255)) == 1.0
    assert color.white_fraction(_solid(0, 0, 0)) == 0.0
    # Saturated blue is bright-ish but not white.
    assert color.white_fraction(_solid(255, 0, 0)) == 0.0


def test_gray_fraction_detects_midtone_gray():
    assert color.gray_fraction(_solid(128, 128, 128)) == 1.0
    assert color.gray_fraction(_solid(255, 255, 255)) == 0.0  # too bright
    assert color.gray_fraction(_solid(255, 0, 0)) == 0.0  # too saturated


def test_orange_fraction_detects_fire_colour():
    # BGR orange (low blue, mid green, high red).
    assert color.orange_fraction(_solid(20, 120, 240)) > 0.9
    assert color.orange_fraction(_solid(128, 128, 128)) == 0.0


def test_saturation_extremes():
    assert color.mean_saturation(_solid(0, 0, 0)) == 0.0  # undefined -> 0
    assert color.mean_saturation(_solid(255, 0, 0)) == 1.0  # fully saturated
