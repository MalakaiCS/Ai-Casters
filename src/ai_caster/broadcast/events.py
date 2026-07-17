"""Broadcast-control bus events."""

from __future__ import annotations

from dataclasses import dataclass

from ai_caster.core.events import Event


@dataclass(frozen=True)
class BroadcastStateChanged(Event):
    """The top-level broadcast state changed.

    ``casting`` is whether the capture→vision→commentary pipeline is live;
    ``muted`` reflects the master mute; ``detail`` carries a human-readable reason.
    """

    casting: bool = False
    muted: bool = False
    detail: str = ""
