"""External capture-card capture via OpenCV.

Reads frames from a video capture device (e.g. an HDMI capture card carrying the
tournament observer feed) using ``cv2.VideoCapture``.
"""

from __future__ import annotations

import numpy as np

from ai_caster.capture.source import FrameSource


class CaptureCardFrameSource(FrameSource):
    """Captures from an OpenCV video device index."""

    def __init__(
        self,
        device_index: int = 0,
        width: int = 0,
        height: int = 0,
        name: str = "capture_card",
    ) -> None:
        super().__init__(name)
        self._device_index = device_index
        self._width = width
        self._height = height
        self._cap = None

    def _on_open(self) -> None:
        try:
            import cv2  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without OpenCV
            raise RuntimeError(
                "Capture-card input requires OpenCV. Install capture extras: "
                'pip install "ai-esports-caster[capture]"'
            ) from exc

        self._cap = cv2.VideoCapture(self._device_index)
        if not self._cap.isOpened():
            self._cap = None
            raise RuntimeError(f"Could not open capture device index {self._device_index}.")
        if self._width and self._height:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)

    def _grab(self) -> np.ndarray | None:
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        return frame  # OpenCV already returns BGR

    def _on_close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
