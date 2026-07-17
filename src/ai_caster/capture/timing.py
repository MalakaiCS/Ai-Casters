"""Capture timing: pacing to a target FPS and measuring the real rate.

The pacing math is separated from the actual sleeping so it can be tested
deterministically with an injected clock. :class:`FrameClock` answers "how long
until the next frame is due"; :class:`FpsMeter` reports the rolling measured
rate; :class:`CaptureStats` is the immutable snapshot the UI/diagnostics read.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


class FrameClock:
    """Fixed-rate pacer for a target FPS.

    Given the scheduled start time of the previous frame and the current time,
    :meth:`delay_before_next` returns how long to sleep to hold the target
    cadence (never negative). Falling behind yields ``0.0`` — the loop then runs
    flat out and the measured FPS reveals it can't keep up.
    """

    def __init__(self, target_fps: float) -> None:
        if target_fps <= 0:
            raise ValueError("target_fps must be positive")
        self._target_fps = float(target_fps)
        self._interval = 1.0 / self._target_fps

    @property
    def target_fps(self) -> float:
        return self._target_fps

    @property
    def interval(self) -> float:
        return self._interval

    def delay_before_next(self, last_start: float, now: float) -> float:
        elapsed = now - last_start
        return max(0.0, self._interval - elapsed)


class FpsMeter:
    """Rolling frames-per-second estimate from recent frame timestamps."""

    def __init__(self, window: int = 60) -> None:
        self._timestamps: deque[float] = deque(maxlen=max(2, window))

    def tick(self, now: float) -> None:
        self._timestamps.append(now)

    @property
    def fps(self) -> float:
        if len(self._timestamps) < 2:
            return 0.0
        span = self._timestamps[-1] - self._timestamps[0]
        if span <= 0:
            return 0.0
        return (len(self._timestamps) - 1) / span

    def reset(self) -> None:
        self._timestamps.clear()


@dataclass(frozen=True)
class CaptureStats:
    """Immutable snapshot of pipeline health."""

    source: str = ""
    running: bool = False
    target_fps: float = 0.0
    actual_fps: float = 0.0
    frames_captured: int = 0
    frames_dropped: int = 0
    avg_capture_ms: float = 0.0
    last_index: int = -1
    uptime_seconds: float = 0.0

    @property
    def drop_rate(self) -> float:
        total = self.frames_captured + self.frames_dropped
        return self.frames_dropped / total if total else 0.0
