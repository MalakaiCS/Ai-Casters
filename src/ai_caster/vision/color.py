"""Vectorised colour statistics over BGR frames (no OpenCV dependency).

The analytic detectors reason about brightness, saturation and hue. Computing
these with NumPy keeps the vision core dependency-light (only NumPy) and fully
testable. Values follow the usual conventions: ``value``/``brightness`` and
``saturation`` are in ``[0, 1]``; hue is in degrees ``[0, 360)``.

These are deliberately simple, fast approximations — good enough for the
effect/scene heuristics. The ONNX detector is the path to precise reads.
"""

from __future__ import annotations

import numpy as np


def _channels(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return float B, G, R channel planes in ``[0, 1]``."""
    arr = bgr.astype(np.float32) / 255.0
    return arr[..., 0], arr[..., 1], arr[..., 2]


def brightness(bgr: np.ndarray) -> float:
    """Mean perceptual brightness (Rec. 601 luma) of a frame/region, ``[0, 1]``."""
    b, g, r = _channels(bgr)
    luma = 0.114 * b + 0.587 * g + 0.299 * r
    return float(luma.mean())


def saturation_map(bgr: np.ndarray) -> np.ndarray:
    """Per-pixel HSV saturation in ``[0, 1]`` (``(max-min)/max``)."""
    arr = bgr.astype(np.float32) / 255.0
    mx = arr.max(axis=-1)
    mn = arr.min(axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        sat = np.where(mx > 0, (mx - mn) / mx, 0.0)
    return sat


def value_map(bgr: np.ndarray) -> np.ndarray:
    """Per-pixel HSV value/brightness (channel max) in ``[0, 1]``."""
    return bgr.astype(np.float32).max(axis=-1) / 255.0


def luma_map(bgr: np.ndarray) -> np.ndarray:
    """Per-pixel Rec. 601 luma in ``[0, 1]``."""
    arr = bgr.astype(np.float32) / 255.0
    return 0.114 * arr[..., 0] + 0.587 * arr[..., 1] + 0.299 * arr[..., 2]


def edge_fraction(bgr: np.ndarray, *, threshold: float = 0.25) -> float:
    """Fraction of strong luma edges — high for crisp text/graphics."""
    lum = luma_map(bgr)
    if lum.shape[0] < 2 or lum.shape[1] < 2:
        return 0.0
    gx = np.abs(np.diff(lum, axis=1))
    gy = np.abs(np.diff(lum, axis=0))
    return float(0.5 * (gx > threshold).mean() + 0.5 * (gy > threshold).mean())


def background_dominance(bgr: np.ndarray, *, tolerance: float = 0.08) -> float:
    """Fraction of pixels close to the region's median luma.

    A text banner sits on a fairly uniform background, so a large share of its
    pixels cluster near one value — unlike busy gameplay, which does not.
    """
    lum = luma_map(bgr)
    if lum.size == 0:
        return 0.0
    median = float(np.median(lum))
    return float((np.abs(lum - median) <= tolerance).mean())


def mean_saturation(bgr: np.ndarray) -> float:
    return float(saturation_map(bgr).mean())


def white_fraction(bgr: np.ndarray, *, value_min: float = 0.85, sat_max: float = 0.15) -> float:
    """Fraction of near-white pixels (bright and desaturated) — flash signature."""
    val = value_map(bgr)
    sat = saturation_map(bgr)
    mask = (val >= value_min) & (sat <= sat_max)
    return float(mask.mean())


def gray_fraction(
    bgr: np.ndarray,
    *,
    value_lo: float = 0.25,
    value_hi: float = 0.75,
    sat_max: float = 0.18,
) -> float:
    """Fraction of mid-tone, low-saturation pixels — smoke signature."""
    val = value_map(bgr)
    sat = saturation_map(bgr)
    mask = (val >= value_lo) & (val <= value_hi) & (sat <= sat_max)
    return float(mask.mean())


def orange_fraction(bgr: np.ndarray) -> float:
    """Fraction of saturated orange/red pixels — molotov/fire signature."""
    b, g, r = _channels(bgr)
    mask = (r > 0.55) & (g > 0.20) & (g < 0.70) & (b < 0.35) & (r - b > 0.30)
    return float(mask.mean())
