"""Generated commentary lines and their bus event."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ai_caster.core.events import Event


@dataclass(frozen=True)
class CommentaryLine:
    """One line of spoken commentary produced from a directive.

    The Voice Engine (M7) turns ``text`` into audio on the channel named by
    ``speaker``.
    """

    speaker: str  # "play_by_play" | "analyst"
    text: str
    topic: str
    excitement: float
    provider: str
    directive_kind: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CommentaryLineGenerated(Event):
    """A commentary line was generated (published on the bus)."""

    line: CommentaryLine | None = None
