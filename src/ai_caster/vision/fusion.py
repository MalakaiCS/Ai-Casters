"""Priority-of-truth fusion.

Encodes the project's core rule — **Server > GSI > Vision > Inference** — as a
small, testable primitive. :func:`fuse` picks the value from the
highest-priority available source; among equal sources, higher confidence wins.
:func:`fuse_effect` applies this to a boolean effect (flashed/smoked/burning):
a confirmed GSI reading always wins, and vision only speaks when GSI is silent —
so *uncertain vision can never override confirmed match data.*
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ai_caster.match.state import DataSource


@dataclass(frozen=True)
class Signal:
    """A candidate value tagged with its source and confidence."""

    value: Any
    source: DataSource
    confidence: float = 1.0


def fuse(signals: Iterable[Signal | None]) -> Signal | None:
    """Return the winning signal by (source priority, then confidence)."""
    best: Signal | None = None
    for signal in signals:
        if signal is None:
            continue
        if best is None or (signal.source, signal.confidence) > (best.source, best.confidence):
            best = signal
    return best


def fuse_effect(
    gsi_value: bool | None,
    vision_active: bool,
    vision_confidence: float,
) -> tuple[bool, DataSource]:
    """Fuse a boolean effect from GSI (authoritative) and vision (fallback).

    Returns the resolved value and the source it came from. When GSI provides a
    value it always wins; vision is consulted only when GSI is ``None``.
    """
    candidates: list[Signal | None] = []
    if gsi_value is not None:
        candidates.append(Signal(bool(gsi_value), DataSource.GSI, 1.0))
    if vision_active:
        candidates.append(Signal(True, DataSource.VISION, vision_confidence))
    winner = fuse(candidates)
    if winner is None:
        return False, DataSource.INFERENCE
    return bool(winner.value), winner.source
