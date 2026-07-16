"""Detect broadcast *lulls* — the gaps a human desk fills with chatter.

Pure functions over the live match model. A lull is any stretch with no live
action to call: a called timeout, a paused match, half-time/intermission, or
warm-up. Freeze-time is deliberately *not* a lull (it's short and the round is
about to start), so the casters don't talk over the buy phase.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_caster.match.model import LiveMatch, Side


@dataclass(frozen=True)
class LullState:
    """The current downtime situation."""

    active: bool
    kind: str = "none"  # timeout | paused | halftime | warmup | none
    timeout_side: Side | None = None

    @property
    def is_timeout(self) -> bool:
        return self.kind == "timeout"


_LULL = LullState(active=False)


def detect_lull(match: LiveMatch | None) -> LullState:
    """Classify the current broadcast lull (if any) from the match model."""
    if match is None:
        return _LULL

    side = match.timeout_side
    if side is not None:
        return LullState(active=True, kind="timeout", timeout_side=side)

    if match.is_paused:
        return LullState(active=True, kind="paused")

    phase = (match.match_phase or "").lower()
    if phase == "intermission":
        return LullState(active=True, kind="halftime")
    if phase == "warmup":
        return LullState(active=True, kind="warmup")

    return _LULL
