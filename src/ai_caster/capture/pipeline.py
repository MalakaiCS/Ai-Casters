"""The capture pipeline: a paced, threaded capture loop.

Owns a :class:`~ai_caster.capture.source.FrameSource` and runs a background loop
that grabs frames at a target FPS, passes them through the GPU-aware uploader,
stores them in a ring buffer, invokes registered frame callbacks, and tracks
timing statistics. It never blocks the UI thread and publishes only coarse
status/stats on the bus (frames go to callbacks, not the bus).

The single-iteration :meth:`capture_once` is separated from the loop so the
pipeline can be driven deterministically in tests without real timing.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from ai_caster.capture.buffer import FrameBuffer
from ai_caster.capture.events import CaptureStatsUpdated, CaptureStatusChanged
from ai_caster.capture.frame import Frame
from ai_caster.capture.source import FrameSource
from ai_caster.capture.timing import CaptureStats, FpsMeter, FrameClock
from ai_caster.capture.uploader import CpuUploader, FrameUploader
from ai_caster.core.events import EventBus
from ai_caster.core.interfaces import Service
from ai_caster.core.logging import get_logger

_log = get_logger("capture.pipeline")

FrameCallback = Callable[[Frame], None]
_EMA_ALPHA = 0.1


class CapturePipeline(Service):
    """Threaded, FPS-paced capture loop over a :class:`FrameSource`."""

    def __init__(
        self,
        source: FrameSource,
        event_bus: EventBus | None = None,
        *,
        target_fps: int = 60,
        buffer_size: int = 8,
        uploader: FrameUploader | None = None,
        stats_interval: float = 1.0,
    ) -> None:
        self._source = source
        self._bus = event_bus
        self._clock = FrameClock(target_fps)
        self._buffer = FrameBuffer(buffer_size)
        self._fps = FpsMeter(window=max(2, target_fps))
        self._uploader = uploader or CpuUploader()
        self._stats_interval = stats_interval

        self._callbacks: list[FrameCallback] = []
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

        # Counters (guarded by _lock).
        self._frames_captured = 0
        self._frames_dropped = 0
        self._avg_capture_ms = 0.0
        self._last_index = -1
        self._started_at = 0.0
        self._last_stats_publish = 0.0

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @property
    def source(self) -> FrameSource:
        return self._source

    @property
    def target_fps(self) -> float:
        return self._clock.target_fps

    @property
    def device(self) -> str:
        return self._uploader.device

    @property
    def buffer(self) -> FrameBuffer:
        return self._buffer

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def latest_frame(self) -> Frame | None:
        return self._buffer.latest()

    def add_frame_callback(self, callback: FrameCallback) -> Callable[[], None]:
        """Register a per-frame callback (invoked on the capture thread)."""
        with self._lock:
            self._callbacks.append(callback)

        def _remove() -> None:
            with self._lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)

        return _remove

    def stats(self) -> CaptureStats:
        with self._lock:
            uptime = (time.monotonic() - self._started_at) if self._started_at else 0.0
            return CaptureStats(
                source=self._source.name,
                running=self.is_running,
                target_fps=self._clock.target_fps,
                actual_fps=round(self._fps.fps, 2),
                frames_captured=self._frames_captured,
                frames_dropped=self._frames_dropped,
                avg_capture_ms=round(self._avg_capture_ms, 3),
                last_index=self._last_index,
                uptime_seconds=round(uptime, 3),
            )

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Open the source and start the capture thread. Idempotent."""
        if self.is_running:
            return
        try:
            self._source.open()
        except Exception as exc:  # noqa: BLE001 - surface source failures to the UI
            _log.exception("Failed to open capture source '%s'", self._source.name)
            self._publish_status(False, f"Failed to open source: {exc}")
            raise

        with self._lock:
            self._reset_counters()
            self._started_at = time.monotonic()
        self._buffer.clear()
        self._fps.reset()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="capture", daemon=True)
        self._thread.start()
        _log.info("Capture started (source=%s, target=%.0ffps)", self._source.name, self.target_fps)
        self._publish_status(True, "started")

    def stop(self) -> None:
        """Signal the loop to stop, join it and close the source. Idempotent."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            if thread.is_alive():
                _log.warning("Capture thread did not stop within timeout")
        self._thread = None
        self._source.close()
        _log.info("Capture stopped (source=%s)", self._source.name)
        self._publish_status(False, "stopped")

    # ------------------------------------------------------------------ #
    # Core iteration
    # ------------------------------------------------------------------ #
    def capture_once(self) -> Frame | None:
        """Grab, process and dispatch a single frame. Never sleeps."""
        t0 = time.monotonic()
        frame = self._source.read()
        if frame is None:
            with self._lock:
                self._frames_dropped += 1
            return None

        frame = self._uploader.upload(frame)
        capture_ms = (time.monotonic() - t0) * 1000.0

        self._buffer.append(frame)
        with self._lock:
            self._frames_captured += 1
            self._last_index = frame.index
            self._avg_capture_ms = (
                capture_ms
                if self._frames_captured == 1
                else self._avg_capture_ms + _EMA_ALPHA * (capture_ms - self._avg_capture_ms)
            )
            callbacks = list(self._callbacks)
        self._fps.tick(frame.timestamp_monotonic)

        for callback in callbacks:
            try:
                callback(frame)
            except Exception:  # noqa: BLE001 - isolate consumer failures
                _log.exception("Frame callback failed")
        return frame

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            last_start = time.monotonic()
            try:
                self.capture_once()
            except Exception:  # noqa: BLE001 - keep the loop alive through transient errors
                _log.exception("Capture iteration failed")
            self._maybe_publish_stats()
            delay = self._clock.delay_before_next(last_start, time.monotonic())
            if delay > 0:
                # Wait interruptibly so stop() is responsive.
                self._stop.wait(delay)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _reset_counters(self) -> None:
        self._frames_captured = 0
        self._frames_dropped = 0
        self._avg_capture_ms = 0.0
        self._last_index = -1
        self._last_stats_publish = 0.0

    def _maybe_publish_stats(self) -> None:
        if self._bus is None:
            return
        now = time.monotonic()
        if now - self._last_stats_publish >= self._stats_interval:
            self._last_stats_publish = now
            self._bus.publish(CaptureStatsUpdated(stats=self.stats()))

    def _publish_status(self, running: bool, detail: str) -> None:
        if self._bus is not None:
            self._bus.publish(
                CaptureStatusChanged(running=running, source=self._source.name, detail=detail)
            )
