"""Optional ONNX model-backed object detector.

This is the production-accuracy path: a user-supplied ONNX detection model (e.g.
a YOLO-family model trained on CS2 HUD/kill-feed/icon crops) run via
``onnxruntime``. No weights ship with the project — you point ``model_path`` at
your own model. Without ``onnxruntime`` installed or a model file present,
:meth:`load` raises a clear error and the pipeline simply runs the analytic
detectors instead.

The output parser targets the common ``[N, 6]`` ``(x1, y1, x2, y2, score, class)``
layout and is defensive: an unexpected output shape yields no observations rather
than a crash.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ai_caster.core.logging import get_logger
from ai_caster.vision.detectors.base import VisionDetector, clamp01
from ai_caster.vision.observations import ObservationKind, VisionObservation

_log = get_logger("vision.onnx")


class OnnxObjectDetector(VisionDetector):
    """Runs a user-provided ONNX detection model. Loaded lazily."""

    name = "onnx"

    def __init__(
        self,
        model_path: str,
        *,
        input_size: tuple[int, int] = (640, 640),
        score_threshold: float = 0.5,
        use_gpu: bool = True,
    ) -> None:
        self._model_path = model_path
        self._input_size = input_size
        self._score_threshold = score_threshold
        self._use_gpu = use_gpu
        self._session = None

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    def load(self) -> None:
        """Create the inference session. Raises a clear error if unavailable."""
        if self.is_loaded:
            return
        if not self._model_path:
            raise RuntimeError("No ONNX model_path configured for the object detector.")
        if not Path(self._model_path).is_file():
            raise RuntimeError(f"ONNX model not found: {self._model_path}")
        try:
            import onnxruntime  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without onnxruntime
            raise RuntimeError(
                "ONNX object detection requires onnxruntime. Install vision extras: "
                'pip install "ai-esports-caster[vision]"'
            ) from exc

        providers = ["CPUExecutionProvider"]
        if self._use_gpu and "CUDAExecutionProvider" in onnxruntime.get_available_providers():
            providers.insert(0, "CUDAExecutionProvider")
        self._session = onnxruntime.InferenceSession(self._model_path, providers=providers)
        _log.info("Loaded ONNX model %s (providers=%s)", self._model_path, providers)

    def detect(self, image: np.ndarray, frame_index: int) -> list[VisionObservation]:
        if self._session is None:
            return []
        tensor = self._preprocess(image)
        input_name = self._session.get_inputs()[0].name
        outputs = self._session.run(None, {input_name: tensor})
        return self._parse(outputs, frame_index)

    # ------------------------------------------------------------------ #
    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        # Nearest-neighbour resize to the model's input size (dependency-free),
        # BGR->RGB, CHW, normalised, batched.
        target_w, target_h = self._input_size
        h, w = image.shape[:2]
        ys = (np.linspace(0, h - 1, target_h)).astype(np.int64)
        xs = (np.linspace(0, w - 1, target_w)).astype(np.int64)
        resized = image[ys][:, xs]
        rgb = resized[:, :, ::-1].astype(np.float32) / 255.0
        chw = np.transpose(rgb, (2, 0, 1))
        return chw[np.newaxis, ...]

    def _parse(self, outputs: list, frame_index: int) -> list[VisionObservation]:
        if not outputs:
            return []
        detections = np.asarray(outputs[0])
        detections = np.squeeze(detections)
        if detections.ndim != 2 or detections.shape[1] < 6:
            _log.debug("Unexpected ONNX output shape %s; skipping.", detections.shape)
            return []
        observations: list[VisionObservation] = []
        for row in detections:
            score = float(row[4])
            if score < self._score_threshold:
                continue
            observations.append(
                VisionObservation(
                    kind=ObservationKind.OBJECT,
                    confidence=clamp01(score),
                    frame_index=frame_index,
                    value=int(row[5]),
                    detail={"box": [float(v) for v in row[:4]]},
                )
            )
        return observations
