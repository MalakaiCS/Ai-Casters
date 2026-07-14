"""Commentary directives — the Director's output.

A directive is an instruction to a *speaker role* (play-by-play or analyst): what
to talk about, how urgently, how energetically, and whether it interrupts what is
currently being said. It carries a ``context`` dict of facts (names, teams, …)
for the word-generating AIs in M6 — the Director itself writes no prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any

from ai_caster.core.events import Event


class Speaker(StrEnum):
    PLAY_BY_PLAY = "play_by_play"
    ANALYST = "analyst"
    NONE = "none"  # deliberate silence


class DirectiveKind(StrEnum):
    CALL = "call"  # play-by-play calls live action
    ANALYZE = "analyze"  # analyst provides analysis
    HANDOFF = "handoff"  # pass the mic (e.g. PBP -> analyst after a round)
    SILENCE = "silence"  # explicitly stay quiet
    REPLAY_ANALYZE = "replay_analyze"  # analyst talks over a replay
    REPLAY_RETURN = "replay_return"  # replay ended; return to live


class DirectivePriority(IntEnum):
    AMBIENT = 0
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True)
class CommentaryDirective:
    """One broadcast-flow decision."""

    speaker: Speaker
    kind: DirectiveKind
    priority: DirectivePriority
    excitement: float
    topic: str
    interrupt: bool = False
    reason: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def is_silence(self) -> bool:
        return self.kind is DirectiveKind.SILENCE or self.speaker is Speaker.NONE


@dataclass(frozen=True)
class CommentaryDirectiveIssued(Event):
    """A directive was issued by the Director (published on the bus)."""

    directive: CommentaryDirective | None = None
