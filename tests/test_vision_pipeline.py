"""Tests for the vision pipeline (analysis, throttling, capture integration)."""

from __future__ import annotations

import numpy as np

from ai_caster.capture.frame import Frame
from ai_caster.capture.pipeline import CapturePipeline
from ai_caster.capture.source import SyntheticFrameSource
from ai_caster.core.events import EventBus
from ai_caster.vision.detectors import FlashDetector, SceneClassifier
from ai_caster.vision.events import VisionStateUpdated
from ai_caster.vision.pipeline import VisionPipeline, downscale


def _white_frame(index: int, w: int = 64, h: int = 48) -> Frame:
    data = np.full((h, w, 3), 255, dtype=np.uint8)
    return Frame(index, data, float(index), float(index), "test")


def test_downscale_reduces_width_and_keeps_aspect():
    img = np.zeros((200, 400, 3), dtype=np.uint8)
    out = downscale(img, 100)
    assert out.shape[1] == 100
    assert out.shape[0] == 50  # aspect preserved


def test_downscale_noop_when_small():
    img = np.zeros((10, 20, 3), dtype=np.uint8)
    assert downscale(img, 100).shape == img.shape


def test_analyze_produces_state():
    pipeline = VisionPipeline([FlashDetector(), SceneClassifier()], min_confidence=0.6)
    state = pipeline.analyze(np.full((48, 64, 3), 255, dtype=np.uint8), frame_index=7)
    assert state.frame_index == 7
    assert state.flash.active is True


def test_process_frame_respects_enabled():
    pipeline = VisionPipeline([FlashDetector()], enabled=False)
    assert pipeline.process_frame(_white_frame(0)) is None
    pipeline.set_enabled(True)
    assert pipeline.process_frame(_white_frame(1)) is not None


def test_process_frame_throttles():
    ticks = iter([0.0, 0.05, 0.2])  # interval for 10 fps is 0.1s
    pipeline = VisionPipeline(
        [FlashDetector()], process_fps=10, enabled=True, clock=lambda: next(ticks)
    )
    assert pipeline.process_frame(_white_frame(0)) is not None  # first always processes
    assert pipeline.process_frame(_white_frame(1)) is None  # 0.05 since last -> skipped
    assert pipeline.process_frame(_white_frame(2)) is not None  # 0.2 -> processed
    assert pipeline.processed_count == 2


def test_process_frame_publishes_state():
    bus = EventBus()
    events: list[VisionStateUpdated] = []
    bus.subscribe(VisionStateUpdated, events.append)
    pipeline = VisionPipeline([FlashDetector()], bus, process_fps=1000, enabled=True)
    pipeline.process_frame(_white_frame(0))
    assert len(events) == 1
    assert events[0].state.flash.active is True


def test_attach_to_capture_pipeline():
    import itertools

    ticks = itertools.count(0.0, 1.0)  # advance 1s per call so throttle never skips
    capture = CapturePipeline(SyntheticFrameSource(64, 48), target_fps=60)
    vision = VisionPipeline(
        [SceneClassifier()], process_fps=1, enabled=True, clock=lambda: next(ticks)
    )
    detach = vision.attach(capture)

    capture.source.open()
    capture.capture_once()
    capture.capture_once()
    assert vision.processed_count == 2
    assert vision.latest_state() is not None

    detach()
    capture.capture_once()
    assert vision.processed_count == 2  # no longer receiving frames
    capture.source.close()
