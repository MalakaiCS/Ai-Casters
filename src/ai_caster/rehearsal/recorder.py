"""Record a live GSI feed to a replayable clip file.

The recorder is installed as a tap on :class:`~ai_caster.gsi.receiver.GSIReceiver`
and is handed every authenticated live payload. It writes one JSON object per line
(``{"t": <seconds since first frame>, "payload": {...}}``) so a clip is a plain,
diff-friendly ``.jsonl``. The GSI ``auth`` block is stripped before writing — the
shared token never lands in a recording — and replay doesn't need it.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

from ai_caster.core.logging import get_logger

_log = get_logger("rehearsal.recorder")


class GsiRecorder:
    """Append-only writer for GSI capture clips (thread-safe)."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._handle = None
        self._path: Path | None = None
        self._start: float | None = None
        self._count = 0

    # ------------------------------------------------------------------ #
    @property
    def is_recording(self) -> bool:
        return self._handle is not None

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def frame_count(self) -> int:
        return self._count

    # ------------------------------------------------------------------ #
    def start(self, path: str | Path) -> Path:
        """Begin a new recording at ``path`` (creating parent folders)."""
        path = Path(path)
        with self._lock:
            if self._handle is not None:
                self._close_locked()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = path.open("w", encoding="utf-8")
            self._path = path
            self._start = None
            self._count = 0
        _log.info("Rehearsal recording started: %s", path)
        return path

    def record(self, payload: dict) -> None:
        """Write one payload. Safe to call when not recording (no-op)."""
        with self._lock:
            if self._handle is None:
                return
            now = self._clock()
            if self._start is None:
                self._start = now
            entry = {
                "t": round(now - self._start, 4),
                "payload": _strip_auth(payload),
            }
            try:
                self._handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
                self._handle.flush()
                self._count += 1
            except (OSError, TypeError, ValueError):
                _log.exception("Failed to write rehearsal frame")

    def stop(self) -> Path | None:
        """Close the recording and return its path (or None if not recording)."""
        with self._lock:
            path = self._path
            self._close_locked()
        if path is not None:
            _log.info("Rehearsal recording stopped: %s (%d frames)", path, self._count)
        return path

    # ------------------------------------------------------------------ #
    def _close_locked(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:  # pragma: no cover - best effort
                pass
        self._handle = None


def _strip_auth(payload: dict) -> dict:
    """Drop the GSI ``auth`` block so the shared token isn't persisted."""
    if not isinstance(payload, dict) or "auth" not in payload:
        return payload
    return {key: value for key, value in payload.items() if key != "auth"}
