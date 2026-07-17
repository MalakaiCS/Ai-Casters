"""Subscription duration presets for the Team panel.

A manager grants a tier for a fixed window (or forever). These presets map a
friendly label to an expiry timestamp computed from "now"; ``lifetime`` means no
expiry (a perpetual grant).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class DurationPreset:
    """A named subscription length. ``days`` of None means perpetual."""

    label: str
    days: int | None

    def expires_at(self, *, now: datetime | None = None) -> datetime | None:
        """Absolute expiry for this preset, or None for a lifetime grant."""
        if self.days is None:
            return None
        return (now or datetime.now(UTC)) + timedelta(days=self.days)


DURATION_PRESETS: tuple[DurationPreset, ...] = (
    DurationPreset("1 day", 1),
    DurationPreset("7 days", 7),
    DurationPreset("30 days", 30),
    DurationPreset("90 days", 90),
    DurationPreset("1 year", 365),
    DurationPreset("Lifetime", None),
)

DEFAULT_DURATION = DURATION_PRESETS[2]  # 30 days
