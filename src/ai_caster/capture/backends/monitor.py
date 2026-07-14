"""Monitor / screen-region capture via `mss`.

Grabs a whole monitor (or a sub-region of it) — the usual way to capture a CS2
observer client running full-screen on a second display.
"""

from __future__ import annotations

import numpy as np

from ai_caster.capture.source import FrameSource


class MonitorFrameSource(FrameSource):
    """Captures a monitor (or region) using the `mss` screen-grab library."""

    def __init__(
        self,
        monitor_index: int = 1,
        region: dict | None = None,
        name: str = "monitor",
    ) -> None:
        super().__init__(name)
        self._monitor_index = monitor_index
        self._region = region
        self._sct = None
        self._grab_region: dict | None = None

    def _on_open(self) -> None:
        try:
            import mss  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without mss
            raise RuntimeError(
                "Monitor capture requires the 'mss' package. Install capture extras: "
                'pip install "ai-esports-caster[capture]"'
            ) from exc

        self._sct = mss.mss()
        monitors = self._sct.monitors  # index 0 = virtual full, 1.. = each monitor
        if self._region and self._region.get("width") and self._region.get("height"):
            self._grab_region = self._region
        else:
            if self._monitor_index >= len(monitors):
                raise RuntimeError(
                    f"Monitor {self._monitor_index} not found; {len(monitors) - 1} available."
                )
            self._grab_region = monitors[self._monitor_index]

    def _grab(self) -> np.ndarray | None:
        raw = self._sct.grab(self._grab_region)  # type: ignore[union-attr]
        # mss returns BGRA; drop the alpha channel to get BGR.
        return np.array(raw)[:, :, :3]

    def _on_close(self) -> None:
        if self._sct is not None:
            self._sct.close()
            self._sct = None
