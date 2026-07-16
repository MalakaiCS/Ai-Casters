"""Monitor / screen-region capture via `mss`.

Grabs a whole monitor (or a sub-region of it) — the usual way to capture a CS2
observer client running full-screen on a second display.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ai_caster.capture.source import FrameSource


@dataclass(frozen=True)
class MonitorInfo:
    """A screen the operator can capture, as reported by ``mss``."""

    index: int  # mss monitor index (1..N); 0 is the virtual "all monitors" region
    width: int
    height: int
    left: int
    top: int

    @property
    def label(self) -> str:
        if self.index == 0:
            return f"All monitors ({self.width}×{self.height})"
        return f"Monitor {self.index} — {self.width}×{self.height} @ ({self.left},{self.top})"


def available_monitors() -> list[MonitorInfo]:
    """List capturable monitors, or an empty list if ``mss`` isn't available.

    Never raises: on a headless/CI box (or before capture extras are installed)
    this returns ``[]`` so the UI can fall back to a plain index spinner.
    """
    try:
        import mss  # type: ignore
    except Exception:  # noqa: BLE001 - mss missing or platform unsupported
        return []
    try:
        with mss.mss() as sct:
            monitors = sct.monitors  # index 0 = virtual full, 1.. = each monitor
    except Exception:  # noqa: BLE001 - no display / grab backend
        return []
    infos: list[MonitorInfo] = []
    for index, mon in enumerate(monitors):
        infos.append(
            MonitorInfo(
                index=index,
                width=int(mon.get("width", 0)),
                height=int(mon.get("height", 0)),
                left=int(mon.get("left", 0)),
                top=int(mon.get("top", 0)),
            )
        )
    return infos


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
