"""Low-frequency capture events published on the bus.

Individual frames are **not** published on the bus — at 60 fps that would be far
too chatty and would couple high-rate capture to every subscriber. High-rate
consumers (the vision system in M4) register a direct frame callback on the
pipeline instead. Only coarse status and ~1 Hz stats go on the bus, which is all
the UI and diagnostics need.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_caster.core.events import Event


@dataclass(frozen=True)
class CaptureStatusChanged(Event):
    """The capture pipeline started or stopped (or failed to start)."""

    running: bool = False
    source: str = ""
    detail: str = ""


@dataclass(frozen=True)
class CaptureStatsUpdated(Event):
    """Periodic pipeline health snapshot (~1 Hz).

    ``stats`` is an immutable :class:`~ai_caster.capture.timing.CaptureStats`;
    typed ``Any`` to keep :mod:`core`-adjacent code import-cycle free.
    """

    stats: Any = None
