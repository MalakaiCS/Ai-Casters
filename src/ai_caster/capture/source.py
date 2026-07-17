"""Frame sources.

A :class:`FrameSource` is anything that yields frames one at a time: a monitor,
a window, a capture card, or the :class:`SyntheticFrameSource` used for
development and headless CI. The pipeline depends only on this interface, so
swapping the real observer feed for a synthetic one requires no pipeline change.

Real hardware/OS backends live in :mod:`ai_caster.capture.backends` and lazily
import their heavy dependencies, so importing this module never requires OpenCV
or mss to be installed.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

import numpy as np

from ai_caster.capture.frame import Frame


class FrameSource(ABC):
    """Abstract capture source with an explicit open/read/close lifecycle."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._is_open = False
        self._index = -1

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_open(self) -> bool:
        return self._is_open

    # -- lifecycle ------------------------------------------------------- #
    def open(self) -> None:
        """Acquire the underlying resource. Idempotent."""
        if self._is_open:
            return
        self._on_open()
        self._is_open = True

    def close(self) -> None:
        """Release the underlying resource. Idempotent."""
        if not self._is_open:
            return
        try:
            self._on_close()
        finally:
            self._is_open = False

    def read(self) -> Frame | None:
        """Grab the next frame, or ``None`` if one is not available this tick."""
        if not self._is_open:
            raise RuntimeError(f"FrameSource '{self._name}' read before open()")
        array = self._grab()
        if array is None:
            return None
        self._index += 1
        return Frame(
            index=self._index,
            data=array,
            timestamp_monotonic=time.monotonic(),
            timestamp_wall=time.time(),
            source=self._name,
        )

    # -- subclass hooks -------------------------------------------------- #
    def _on_open(self) -> None:  # pragma: no cover - trivial default
        return None

    def _on_close(self) -> None:  # pragma: no cover - trivial default
        return None

    @abstractmethod
    def _grab(self) -> np.ndarray | None:
        """Return the next ``H x W x 3`` uint8 BGR array, or ``None``."""
        raise NotImplementedError


class SyntheticFrameSource(FrameSource):
    """Generates deterministic frames without any display or hardware.

    Each frame is a solid BGR field whose value encodes the frame index (so
    tests can assert on content) with a moving diagonal band, giving the vision
    stack something with motion to work against later. This is the default
    source, which is what lets the whole application run on any machine.
    """

    def __init__(self, width: int = 1920, height: int = 1080, name: str = "synthetic") -> None:
        super().__init__(name)
        self._width = int(width)
        self._height = int(height)

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def _grab(self) -> np.ndarray:
        idx = self._index + 1
        frame = np.empty((self._height, self._width, 3), dtype=np.uint8)
        # Encode the index in the blue channel so it is recoverable in tests.
        frame[:, :, 0] = idx % 256
        frame[:, :, 1] = (idx * 2) % 256
        frame[:, :, 2] = (idx * 3) % 256
        # A moving diagonal band gives inter-frame motion.
        band = (idx * 7) % max(self._width, 1)
        frame[:, max(0, band - 2) : band + 2, :] = 255
        return frame
