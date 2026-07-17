"""Load and replay a recorded GSI clip through the receiver.

The scheduling core (:func:`schedule`) is pure — it turns a clip and a speed into
a list of ``(delay, payload)`` steps — so playback timing is unit-tested with no
threads. :class:`RehearsalPlayer` runs those steps on a worker thread, feeding
each payload to a sink (the receiver's ``replay_payload``) and sleeping the
inter-frame delay, interruptibly. Speed ``<= 0`` means "instant" (no waiting).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_caster.core.logging import get_logger

_log = get_logger("rehearsal.player")


@dataclass(frozen=True)
class RehearsalFrame:
    """One recorded payload and when it occurred (seconds from the clip start)."""

    t: float
    payload: dict


@dataclass(frozen=True)
class RehearsalClip:
    """A loaded recording."""

    frames: tuple[RehearsalFrame, ...]
    source: str = ""

    def __len__(self) -> int:
        return len(self.frames)

    @property
    def duration(self) -> float:
        return self.frames[-1].t if self.frames else 0.0


def load_clip(path: str | Path) -> RehearsalClip:
    """Parse a ``.jsonl`` clip, tolerating blank or malformed lines."""
    path = Path(path)
    frames: list[RehearsalFrame] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
                payload = entry["payload"]
                t = float(entry.get("t", 0.0))
            except (ValueError, KeyError, TypeError):
                _log.warning("Skipping malformed rehearsal line %d in %s", number, path.name)
                continue
            if isinstance(payload, dict):
                frames.append(RehearsalFrame(t=t, payload=payload))
    # Monotonic timestamps guard against a bad clip that would sleep negatively.
    frames.sort(key=lambda f: f.t)
    return RehearsalClip(frames=tuple(frames), source=str(path))


def schedule(clip: RehearsalClip, speed: float = 1.0) -> list[tuple[float, dict]]:
    """Turn a clip into ``(delay_before_this_frame, payload)`` steps.

    ``speed`` scales real time (2.0 = twice as fast). ``speed <= 0`` yields zero
    delays (instant replay). Delays are clamped at 0 so a non-monotonic clip can
    never sleep backwards.
    """
    steps: list[tuple[float, dict]] = []
    prev_t = 0.0
    for frame in clip.frames:
        if speed <= 0:
            delay = 0.0
        else:
            delay = max(0.0, (frame.t - prev_t) / speed)
        steps.append((delay, frame.payload))
        prev_t = frame.t
    return steps


class RehearsalPlayer:
    """Replays a clip on a worker thread, feeding payloads to a sink."""

    def __init__(
        self,
        sink: Callable[[dict], object],
        *,
        on_progress: Callable[[int, int], None] | None = None,
        on_finished: Callable[[bool], None] | None = None,
        sleep: Callable[[float], bool] | None = None,
    ) -> None:
        """``sink`` receives each payload. ``sleep(delay)`` should return True to
        abort early (defaults to an interruptible wait on the stop event)."""
        self._sink = sink
        self._on_progress = on_progress
        self._on_finished = on_finished
        self._sleep = sleep
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._played = 0
        self._total = 0

    def set_callbacks(
        self,
        *,
        on_progress: Callable[[int, int], None] | None = None,
        on_finished: Callable[[bool], None] | None = None,
    ) -> None:
        """Attach progress/finished callbacks (e.g. to drive a UI). Fired on the
        worker thread, so a UI must marshal them to its own thread."""
        self._on_progress = on_progress
        self._on_finished = on_finished

    # ------------------------------------------------------------------ #
    @property
    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def progress(self) -> tuple[int, int]:
        with self._lock:
            return self._played, self._total

    # ------------------------------------------------------------------ #
    def play(self, clip: RehearsalClip, *, speed: float = 1.0) -> None:
        """Start replaying ``clip``. Idempotent while a playback is in flight."""
        if self.is_playing or not clip.frames:
            return
        self._stop.clear()
        with self._lock:
            self._played = 0
            self._total = len(clip.frames)
        self._thread = threading.Thread(
            target=self._run, args=(clip, speed), name="rehearsal", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop playback and wait briefly for the worker to exit."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None

    def dispose(self) -> None:
        self.stop()

    # ------------------------------------------------------------------ #
    def _wait(self, delay: float) -> bool:
        if self._sleep is not None:
            return bool(self._sleep(delay))
        if delay <= 0:
            return self._stop.is_set()
        return self._stop.wait(delay)  # True if stopped during the wait

    def _run(self, clip: RehearsalClip, speed: float) -> None:
        completed = False
        try:
            for delay, payload in schedule(clip, speed):
                if self._wait(delay):
                    break
                try:
                    self._sink(payload)
                except Exception:  # noqa: BLE001 - one bad frame shouldn't kill playback
                    _log.exception("Rehearsal sink failed on a frame")
                with self._lock:
                    self._played += 1
                    played, total = self._played, self._total
                if self._on_progress is not None:
                    try:
                        self._on_progress(played, total)
                    except Exception:  # noqa: BLE001 - UI callback isolation
                        _log.exception("Rehearsal progress callback failed")
            else:
                completed = True
        finally:
            if self._on_finished is not None:
                try:
                    self._on_finished(completed)
                except Exception:  # noqa: BLE001 - UI callback isolation
                    _log.exception("Rehearsal finished callback failed")
