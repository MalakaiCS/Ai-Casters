"""Replay state model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ReplayType(StrEnum):
    """The kind of moment being replayed (as reported by the replay system)."""

    GENERIC = "generic"
    KILL = "kill"
    MULTIKILL = "multikill"
    CLUTCH = "clutch"
    ROUND = "round"
    HIGHLIGHT = "highlight"


@dataclass(frozen=True)
class ReplayState:
    """Authoritative replay state, driven by external replay events.

    ``active`` is the single fact the rest of the app cares about: when it is
    ``True`` the broadcast is showing replay footage and must never be described
    as live.
    """

    active: bool = False
    replay_type: ReplayType = ReplayType.GENERIC
    speed: float = 1.0
    started_at: datetime | None = None

    @property
    def is_slow_motion(self) -> bool:
        return self.active and self.speed < 1.0
