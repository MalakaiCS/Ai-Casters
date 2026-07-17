"""Module 10 — Commentary Director.

The internal controller responsible for **broadcast flow**: who speaks, when to
interrupt, when to stay silent, replay transitions, excitement level, speech
cancellation and handoffs. It consumes match events, the live model, vision and
replay state, and emits :class:`CommentaryDirective` decisions.

It **never produces spoken commentary** — it only decides. The Play-by-Play and
Analyst AIs (M6) turn directives into words; the Voice Engine (M7) speaks them.
"""

from ai_caster.director.directives import (
    CommentaryDirective,
    CommentaryDirectiveIssued,
    DirectiveKind,
    DirectivePriority,
    Speaker,
)
from ai_caster.director.director import CommentaryDirector

__all__ = [
    "CommentaryDirector",
    "CommentaryDirective",
    "CommentaryDirectiveIssued",
    "DirectiveKind",
    "DirectivePriority",
    "Speaker",
]
