"""A thread-safe fixed-capacity ring buffer of frames.

The pipeline keeps a short look-back window of recent frames so downstream
consumers (vision, replay/trade context in later milestones) can inspect not
just the latest frame but the last N. Oldest frames are evicted automatically.
"""

from __future__ import annotations

import threading
from collections import deque

from ai_caster.capture.frame import Frame


class FrameBuffer:
    """Bounded, thread-safe ring buffer with latest-frame access."""

    def __init__(self, capacity: int = 8) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        self._frames: deque[Frame] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def append(self, frame: Frame) -> None:
        with self._lock:
            self._frames.append(frame)

    def latest(self) -> Frame | None:
        with self._lock:
            return self._frames[-1] if self._frames else None

    def snapshot(self) -> list[Frame]:
        """Return the buffered frames oldest→newest (a shallow copy)."""
        with self._lock:
            return list(self._frames)

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames)
