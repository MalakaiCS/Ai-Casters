"""Module 6 — Video Capture.

Captures the CS2 observer feed into a timed, GPU-aware frame pipeline that the
Computer Vision module (M4) consumes. The capture *source* is abstracted
(:class:`FrameSource`) so the pipeline is identical whether pixels come from a
monitor, a window, a capture card, or the synthetic generator used for
development and headless CI.
"""

from ai_caster.capture.frame import Frame
from ai_caster.capture.pipeline import CapturePipeline
from ai_caster.capture.source import FrameSource, SyntheticFrameSource

__all__ = ["Frame", "CapturePipeline", "FrameSource", "SyntheticFrameSource"]
