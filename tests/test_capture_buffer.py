"""Tests for the frame ring buffer."""

from __future__ import annotations

import numpy as np
import pytest

from ai_caster.capture.buffer import FrameBuffer
from ai_caster.capture.frame import Frame


def _frame(idx: int) -> Frame:
    return Frame(idx, np.zeros((2, 2, 3), dtype=np.uint8), float(idx), float(idx), "t")


def test_buffer_latest_and_len():
    buf = FrameBuffer(capacity=3)
    assert buf.latest() is None
    assert len(buf) == 0
    buf.append(_frame(0))
    buf.append(_frame(1))
    assert len(buf) == 2
    assert buf.latest().index == 1


def test_buffer_evicts_oldest():
    buf = FrameBuffer(capacity=2)
    for i in range(4):
        buf.append(_frame(i))
    snap = buf.snapshot()
    assert [f.index for f in snap] == [2, 3]  # oldest evicted
    assert len(buf) == 2


def test_buffer_clear():
    buf = FrameBuffer(capacity=2)
    buf.append(_frame(0))
    buf.clear()
    assert len(buf) == 0


def test_buffer_capacity_validation():
    with pytest.raises(ValueError):
        FrameBuffer(0)
