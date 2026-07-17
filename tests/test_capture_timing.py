"""Tests for capture timing helpers."""

from __future__ import annotations

import pytest

from ai_caster.capture.timing import CaptureStats, FpsMeter, FrameClock


def test_frame_clock_interval():
    clock = FrameClock(60)
    assert clock.target_fps == 60
    assert clock.interval == pytest.approx(1 / 60)


def test_frame_clock_delay_math():
    clock = FrameClock(10)  # 0.1s interval
    # Half the interval elapsed -> wait the other half.
    assert clock.delay_before_next(last_start=100.0, now=100.05) == pytest.approx(0.05)
    # Behind schedule -> no wait.
    assert clock.delay_before_next(last_start=100.0, now=100.2) == 0.0


def test_frame_clock_rejects_bad_fps():
    with pytest.raises(ValueError):
        FrameClock(0)


def test_fps_meter_measures_rate():
    meter = FpsMeter(window=10)
    assert meter.fps == 0.0  # not enough samples
    for i in range(11):
        meter.tick(i * 0.1)  # a tick every 100ms -> 10 fps
    assert meter.fps == pytest.approx(10.0, rel=0.05)


def test_capture_stats_drop_rate():
    stats = CaptureStats(frames_captured=90, frames_dropped=10)
    assert stats.drop_rate == pytest.approx(0.1)
    assert CaptureStats().drop_rate == 0.0
