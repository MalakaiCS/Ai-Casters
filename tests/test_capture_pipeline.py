"""Tests for the capture pipeline."""

from __future__ import annotations

import time

import numpy as np

from ai_caster.capture.events import CaptureStatsUpdated, CaptureStatusChanged
from ai_caster.capture.frame import Frame
from ai_caster.capture.pipeline import CapturePipeline
from ai_caster.capture.source import FrameSource, SyntheticFrameSource
from ai_caster.core.events import EventBus


class _FlakySource(FrameSource):
    """Yields a frame, then None, then a frame, ... to exercise drop handling."""

    def __init__(self) -> None:
        super().__init__("flaky")
        self._tick = -1

    def _grab(self):
        self._tick += 1
        if self._tick % 2 == 1:
            return None
        return np.full((2, 2, 3), self._tick, dtype=np.uint8)


class _CountingUploader:
    device = "cpu"

    def __init__(self) -> None:
        self.calls = 0

    def upload(self, frame: Frame) -> Frame:
        self.calls += 1
        return frame


def test_capture_once_buffers_and_calls_back():
    pipeline = CapturePipeline(SyntheticFrameSource(8, 8), buffer_size=4, target_fps=60)
    seen: list[int] = []
    pipeline.add_frame_callback(lambda f: seen.append(f.index))
    pipeline.source.open()

    for _ in range(3):
        pipeline.capture_once()

    assert seen == [0, 1, 2]
    assert pipeline.latest_frame().index == 2
    assert pipeline.stats().frames_captured == 3
    pipeline.source.close()


def test_capture_once_counts_drops():
    pipeline = CapturePipeline(_FlakySource(), target_fps=60)
    pipeline.source.open()
    for _ in range(4):  # frame, None, frame, None
        pipeline.capture_once()
    stats = pipeline.stats()
    assert stats.frames_captured == 2
    assert stats.frames_dropped == 2
    assert stats.drop_rate == 0.5
    pipeline.source.close()


def test_uploader_seam_invoked():
    uploader = _CountingUploader()
    pipeline = CapturePipeline(SyntheticFrameSource(4, 4), uploader=uploader, target_fps=60)
    pipeline.source.open()
    pipeline.capture_once()
    pipeline.capture_once()
    assert uploader.calls == 2
    assert pipeline.device == "cpu"
    pipeline.source.close()


def test_buffer_capped_at_capacity():
    pipeline = CapturePipeline(SyntheticFrameSource(4, 4), buffer_size=2, target_fps=60)
    pipeline.source.open()
    for _ in range(5):
        pipeline.capture_once()
    assert len(pipeline.buffer) == 2
    assert [f.index for f in pipeline.buffer.snapshot()] == [3, 4]
    pipeline.source.close()


def test_callback_removal():
    pipeline = CapturePipeline(SyntheticFrameSource(4, 4), target_fps=60)
    seen: list[int] = []
    remove = pipeline.add_frame_callback(lambda f: seen.append(f.index))
    pipeline.source.open()
    pipeline.capture_once()
    remove()
    pipeline.capture_once()
    assert seen == [0]
    pipeline.source.close()


def test_bad_callback_is_isolated():
    pipeline = CapturePipeline(SyntheticFrameSource(4, 4), target_fps=60)
    good: list[int] = []

    def boom(_f):
        raise RuntimeError("boom")

    pipeline.add_frame_callback(boom)
    pipeline.add_frame_callback(lambda f: good.append(f.index))
    pipeline.source.open()
    pipeline.capture_once()  # must not raise
    assert good == [0]
    pipeline.source.close()


def test_threaded_lifecycle_and_events():
    bus = EventBus()
    statuses: list[CaptureStatusChanged] = []
    stats_events: list[CaptureStatsUpdated] = []
    bus.subscribe(CaptureStatusChanged, statuses.append)
    bus.subscribe(CaptureStatsUpdated, stats_events.append)

    pipeline = CapturePipeline(
        SyntheticFrameSource(16, 16), bus, target_fps=120, stats_interval=0.01
    )
    assert not pipeline.is_running
    pipeline.start()
    assert pipeline.is_running
    time.sleep(0.15)
    pipeline.stop()

    assert not pipeline.is_running
    assert pipeline.stats().frames_captured > 0
    # Started + stopped statuses published.
    assert [s.running for s in statuses][:1] == [True]
    assert statuses[-1].running is False
    assert len(stats_events) >= 1


def test_start_is_idempotent():
    pipeline = CapturePipeline(SyntheticFrameSource(8, 8), target_fps=120)
    pipeline.start()
    pipeline.start()  # no error, still one thread
    assert pipeline.is_running
    pipeline.stop()


def test_snapshot_grabs_a_frame_while_stopped():
    pipeline = CapturePipeline(SyntheticFrameSource(8, 8), target_fps=60)
    assert not pipeline.is_running
    frame = pipeline.snapshot()
    assert frame is not None and frame.is_valid
    # Snapshot must leave the source closed again when capture isn't running.
    assert not pipeline.source.is_open
    assert not pipeline.is_running


def test_set_source_swaps_source_when_stopped():
    pipeline = CapturePipeline(SyntheticFrameSource(8, 8), target_fps=60)
    new_source = SyntheticFrameSource(16, 16, name="swapped")
    pipeline.set_source(new_source)
    assert pipeline.source is new_source
    assert not pipeline.is_running


def test_set_source_restarts_when_running():
    pipeline = CapturePipeline(SyntheticFrameSource(8, 8), target_fps=120)
    pipeline.start()
    try:
        new_source = SyntheticFrameSource(16, 16, name="swapped")
        pipeline.set_source(new_source)
        assert pipeline.source is new_source
        assert pipeline.is_running  # kept running across the swap
    finally:
        pipeline.stop()
