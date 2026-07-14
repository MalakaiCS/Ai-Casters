"""Capture a specific window by title.

Locates the window's on-screen rectangle (via `pygetwindow`) and grabs that
region with `mss`. This targets a windowed CS2 observer client so the operator
doesn't have to dedicate a whole monitor.
"""

from __future__ import annotations

import numpy as np

from ai_caster.capture.source import FrameSource


class WindowFrameSource(FrameSource):
    """Captures the bounding rectangle of a titled window."""

    def __init__(self, window_title: str, name: str = "window") -> None:
        super().__init__(name)
        self._title = window_title
        self._sct = None
        self._window = None

    def _on_open(self) -> None:
        try:
            import mss  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Window capture requires the 'mss' package. Install capture extras: "
                'pip install "ai-esports-caster[capture]"'
            ) from exc
        try:
            import pygetwindow  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Window capture requires the 'pygetwindow' package. Install capture extras: "
                'pip install "ai-esports-caster[capture]"'
            ) from exc

        matches = [w for w in pygetwindow.getAllWindows() if self._title.lower() in w.title.lower()]
        if not matches:
            raise RuntimeError(f"No window matching title '{self._title}' was found.")
        self._window = matches[0]
        self._sct = mss.mss()

    def _grab(self) -> np.ndarray | None:
        window = self._window
        if window is None or self._sct is None:
            return None
        # Skip while the window is minimised (zero/negative size).
        if window.width <= 0 or window.height <= 0:
            return None
        region = {
            "left": int(window.left),
            "top": int(window.top),
            "width": int(window.width),
            "height": int(window.height),
        }
        raw = self._sct.grab(region)
        return np.array(raw)[:, :, :3]

    def _on_close(self) -> None:
        if self._sct is not None:
            self._sct.close()
            self._sct = None
