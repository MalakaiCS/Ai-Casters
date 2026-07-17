"""Tests for the optional ONNX detector's load/guard behaviour.

These exercise the deterministic error paths (no model configured, missing file,
detect-before-load) that hold regardless of whether onnxruntime is installed.
"""

from __future__ import annotations

import numpy as np
import pytest

from ai_caster.vision.detectors.onnx_detector import OnnxObjectDetector


def test_load_without_model_path_raises():
    with pytest.raises(RuntimeError, match="No ONNX model_path"):
        OnnxObjectDetector("").load()


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        OnnxObjectDetector(str(tmp_path / "missing.onnx")).load()


def test_detect_before_load_returns_empty():
    detector = OnnxObjectDetector("model.onnx")
    assert detector.is_loaded is False
    assert detector.detect(np.zeros((10, 10, 3), dtype=np.uint8), 0) == []


def test_factory_skips_onnx_on_bad_path(tmp_path):
    # A configured-but-invalid model path must not crash pipeline construction;
    # the analytic detectors still load.
    from ai_caster.config.models import VisionSettings
    from ai_caster.vision.factory import build_detectors

    settings = VisionSettings(model_path=str(tmp_path / "nope.onnx"))
    detectors = build_detectors(settings)
    names = {d.name for d in detectors}
    assert "flash" in names
    assert "onnx" not in names  # skipped because it could not load
