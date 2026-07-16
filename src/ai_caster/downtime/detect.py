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


def is_live_round(match: LiveMatch | None) -> bool:
    """True when a round is actively being played (not a lull, freeze-time or break).

    This is the window the slow-round filler is allowed to speak in: real live
    action, just without any events to react to. Freeze-time (the buy phase) and
    round-over are excluded so the desk never talks over the reset.
    """
    if match is None or detect_lull(match).active:
        return False
    round_phase = (match.round_phase or "").lower()
    if round_phase and round_phase != "live":
        return False  # freezetime / over
    active = (match.active_phase or "").lower()
    if active and active != "live":
        return False  # timeout/paused/… already caught by detect_lull, but be safe
    return True
