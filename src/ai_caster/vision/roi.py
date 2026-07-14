"""Regions of interest on the observer HUD.

Regions are expressed as **fractions** of the frame (0..1) so they are
resolution-independent — the same layout works at 1080p or 1440p. The values
approximate the CS2 tournament-observer HUD; they are configurable so a
non-standard overlay can be retargeted without code changes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Region:
    """A fractional rectangle on the frame."""

    name: str
    left: float
    top: float
    width: float
    height: float

    def pixels(self, frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
        """Return integer ``(x0, y0, x1, y1)`` clamped to the frame."""
        x0 = int(round(self.left * frame_width))
        y0 = int(round(self.top * frame_height))
        x1 = int(round((self.left + self.width) * frame_width))
        y1 = int(round((self.top + self.height) * frame_height))
        x0 = max(0, min(x0, frame_width))
        x1 = max(x0 + 1, min(x1, frame_width))
        y0 = max(0, min(y0, frame_height))
        y1 = max(y0 + 1, min(y1, frame_height))
        return x0, y0, x1, y1

    def crop(self, frame_data: np.ndarray) -> np.ndarray:
        """Return the sub-image for this region (a view, not a copy)."""
        h, w = frame_data.shape[:2]
        x0, y0, x1, y1 = self.pixels(w, h)
        return frame_data[y0:y1, x0:x1]


# Approximate CS2 observer-HUD regions.
FULL = Region("full", 0.0, 0.0, 1.0, 1.0)
KILL_FEED = Region("kill_feed", 0.74, 0.02, 0.25, 0.30)
SCOREBOARD = Region("scoreboard", 0.32, 0.0, 0.36, 0.09)
BOMB_TIMER = Region("bomb_timer", 0.45, 0.09, 0.10, 0.05)
HUD_BOTTOM = Region("hud_bottom", 0.0, 0.88, 1.0, 0.12)
RADAR = Region("radar", 0.0, 0.0, 0.16, 0.28)
# The central play area, excluding HUD chrome — used for effect detection so the
# HUD's own colours don't bias smoke/flash/fire estimates.
PLAY_AREA = Region("play_area", 0.12, 0.10, 0.76, 0.72)

DEFAULT_REGIONS: dict[str, Region] = {
    r.name: r for r in (FULL, KILL_FEED, SCOREBOARD, BOMB_TIMER, HUD_BOTTOM, RADAR, PLAY_AREA)
}
