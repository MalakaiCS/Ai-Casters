"""The :class:`Frame` — one captured image plus its timing metadata.

Pixels are stored as a NumPy ``uint8`` array in **BGR** channel order (the
OpenCV convention the vision stack will use). Each frame carries a monotonic
timestamp (for latency/FPS math) and a wall-clock timestamp (for logs), a
monotonically increasing index, and the source name — everything downstream
needs to reason about *when* a frame was seen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Frame:
    """An immutable captured frame.

    ``data`` is an ``H x W x 3`` ``uint8`` BGR array. The array itself is not
    copied on construction; producers must not mutate a frame after publishing
    it (the pipeline never does).
    """

    index: int
    data: np.ndarray
    timestamp_monotonic: float
    timestamp_wall: float
    source: str

    @property
    def height(self) -> int:
        return int(self.data.shape[0])

    @property
    def width(self) -> int:
        return int(self.data.shape[1])

    @property
    def channels(self) -> int:
        return int(self.data.shape[2]) if self.data.ndim == 3 else 1

    @property
    def is_valid(self) -> bool:
        return self.data.ndim == 3 and self.data.shape[2] == 3 and self.data.size > 0

    def age_seconds(self, now_monotonic: float) -> float:
        """How stale this frame is relative to a monotonic ``now``."""
        return max(0.0, now_monotonic - self.timestamp_monotonic)

    def to_rgb_bytes(self) -> bytes:
        """Return contiguous RGB bytes (for a Qt ``QImage`` preview).

        Converts BGR→RGB without OpenCV so the UI has no cv2 dependency.
        """
        rgb = np.ascontiguousarray(self.data[:, :, ::-1])
        return rgb.tobytes()
