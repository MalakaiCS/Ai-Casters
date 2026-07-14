"""Tests for the capture source factory and backend dependency handling."""

from __future__ import annotations

import importlib.util

import pytest

from ai_caster.capture.backends.capture_card import CaptureCardFrameSource
from ai_caster.capture.backends.monitor import MonitorFrameSource
from ai_caster.capture.factory import create_frame_source
from ai_caster.capture.source import SyntheticFrameSource
from ai_caster.config.models import CaptureSettings, CaptureSourceType


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def test_factory_builds_synthetic_by_default():
    source = create_frame_source(CaptureSettings())
    assert isinstance(source, SyntheticFrameSource)
    assert source.width == 1920 and source.height == 1080


def test_factory_maps_each_source_type():
    from ai_caster.capture.backends.window import WindowFrameSource

    monitor = create_frame_source(CaptureSettings(source=CaptureSourceType.MONITOR))
    window = create_frame_source(CaptureSettings(source=CaptureSourceType.WINDOW))
    card = create_frame_source(CaptureSettings(source=CaptureSourceType.CAPTURE_CARD))
    assert isinstance(monitor, MonitorFrameSource)
    assert isinstance(window, WindowFrameSource)
    assert isinstance(card, CaptureCardFrameSource)


def test_construction_does_not_import_heavy_deps():
    # Building the source must not require the native library — only open() does.
    MonitorFrameSource(monitor_index=1)
    CaptureCardFrameSource(device_index=0)  # no exception even without OpenCV


@pytest.mark.skipif(_installed("mss"), reason="mss is installed; missing-dep path not exercised")
def test_monitor_open_without_mss_raises_clear_error():
    with pytest.raises(RuntimeError, match="mss"):
        MonitorFrameSource().open()


@pytest.mark.skipif(_installed("cv2"), reason="OpenCV is installed; missing-dep path not exercised")
def test_capture_card_open_without_opencv_raises_clear_error():
    with pytest.raises(RuntimeError, match="OpenCV"):
        CaptureCardFrameSource().open()
