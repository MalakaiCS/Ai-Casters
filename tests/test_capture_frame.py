"""Tests for the Frame model and synthetic source."""

from __future__ import annotations

import numpy as np

from ai_caster.capture.frame import Frame
from ai_caster.capture.source import SyntheticFrameSource


def _frame(idx: int, w: int = 4, h: int = 3) -> Frame:
    return Frame(
        index=idx,
        data=np.zeros((h, w, 3), dtype=np.uint8),
        timestamp_monotonic=100.0,
        timestamp_wall=1.0,
        source="test",
    )


def test_frame_dimensions_and_validity():
    frame = _frame(0, w=8, h=6)
    assert frame.width == 8
    assert frame.height == 6
    assert frame.channels == 3
    assert frame.is_valid


def test_frame_age():
    frame = _frame(0)
    assert frame.age_seconds(100.5) == 0.5
    assert frame.age_seconds(99.0) == 0.0  # never negative


def test_frame_to_rgb_bytes_swaps_channels():
    data = np.zeros((1, 1, 3), dtype=np.uint8)
    data[0, 0] = (10, 20, 30)  # BGR
    frame = Frame(0, data, 0.0, 0.0, "t")
    assert frame.to_rgb_bytes() == bytes((30, 20, 10))  # RGB


def test_synthetic_source_lifecycle_and_indexing():
    source = SyntheticFrameSource(width=32, height=24)
    source.open()
    assert source.is_open
    f0 = source.read()
    f1 = source.read()
    assert f0.index == 0 and f1.index == 1
    assert f0.width == 32 and f0.height == 24
    # Index is encoded in the blue channel (channel 0 of BGR).
    assert int(f1.data[0, 0, 0]) == 1 % 256
    source.close()
    assert not source.is_open


def test_read_before_open_raises():
    source = SyntheticFrameSource()
    try:
        source.read()
    except RuntimeError as exc:
        assert "before open" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_open_close_idempotent():
    source = SyntheticFrameSource()
    source.open()
    source.open()  # no error
    source.close()
    source.close()  # no error
