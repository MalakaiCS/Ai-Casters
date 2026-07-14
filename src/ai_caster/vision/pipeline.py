"""The vision pipeline.

Consumes frames from the capture pipeline (as a registered frame callback),
throttles them to the configured analysis rate, downscales for speed, runs the
enabled detectors, folds their observations into a :class:`VisionState`, and
publishes it on the bus. It is disabled by default and does no work until
enabled, so it never burdens capture when vision isn't wanted.

The pure :meth:`analyze` (image → state) is separated from the throttled,
side-effecting :meth:`process_frame` so detector behaviour is unit-tested without
any timing or bus.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import numpy as np

from ai_caster.capture.frame import Frame
from ai_caster.capture.pipeline import CapturePipeline
from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger
from ai_caster.vision.detectors.base import VisionDetector
from ai_caster.vision.events import VisionStateUpdated
from ai_caster.vision.state import VisionState

_log = get_logger("vision.pipeline")


def downscale(image: np.ndarray, target_width: int) -> np.ndarray:
    """Nearest-neighbour downscale to ``target_width`` (dependency-free).

    Upscaling is avoided: frames already narrower than the target are returned
    unchanged.
    """
    h, w = image.shape[:2]
    if w <= target_width:
        return image
    target_h = max(1, int(round(h * target_width / w)))
    ys = np.linspace(0, h - 1, target_h).astype(np.int64)
    xs = np.linspace(0, w - 1, target_width).astype(np.int64)
    return image[ys][:, xs]


class VisionPipeline:
    """Runs detectors over captured frames and publishes vision state."""

    def __init__(
        self,
        detectors: list[VisionDetector],
        event_bus: EventBus | None = None,
        *,
        min_confidence: float = 0.6,
        process_fps: int = 12,
        downscale_width: int = 640,
        enabled: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._detectors = detectors
        self._bus = event_bus
        self._min_confidence = min_confidence
        self._interval = 1.0 / max(1, process_fps)
        self._downscale_width = downscale_width
        self._enabled = enabled
        self._clock = clock

        self._lock = threading.RLock()
        self._latest: VisionState | None = None
        self._last_process = float("-inf")  # so the first frame always processes
        self._processed = 0
        self._detach: Callable[[], None] | None = None

    # ------------------------------------------------------------------ #
    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def processed_count(self) -> int:
        return self._processed

    @property
    def detector_names(self) -> list[str]:
        return [d.name for d in self._detectors]

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        _log.info("Vision %s", "enabled" if enabled else "disabled")

    def latest_state(self) -> VisionState | None:
        with self._lock:
            return self._latest

    # ------------------------------------------------------------------ #
    def attach(self, capture: CapturePipeline) -> Callable[[], None]:
        """Register as a frame callback on ``capture``. Returns a detacher."""
        self._detach = capture.add_frame_callback(self.process_frame)
        return self._detach

    def detach(self) -> None:
        if self._detach is not None:
            self._detach()
            self._detach = None

    # ------------------------------------------------------------------ #
    def analyze(self, image: np.ndarray, frame_index: int) -> VisionState:
        """Run all detectors over one image and fold the result into a state."""
        observations = []
        for detector in self._detectors:
            try:
                observations.extend(detector.detect(image, frame_index))
            except Exception:  # noqa: BLE001 - one detector must not break the rest
                _log.exception("Detector %s failed", detector.name)
        return VisionState.from_observations(
            frame_index, observations, min_confidence=self._min_confidence
        )

    def process_frame(self, frame: Frame) -> VisionState | None:
        """Throttle, downscale, analyse and publish. Called on the capture thread."""
        if not self._enabled or not frame.is_valid:
            return None
        now = self._clock()
        if now - self._last_process < self._interval:
            return None
        self._last_process = now

        image = downscale(frame.data, self._downscale_width)
        state = self.analyze(image, frame.index)
        with self._lock:
            self._latest = state
            self._processed += 1
        if self._bus is not None:
            self._bus.publish(VisionStateUpdated(state=state))
        return state
