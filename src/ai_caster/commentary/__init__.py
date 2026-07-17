"""Modules 11 & 12 — Play-by-Play AI and Analyst AI.

Two independent commentary generators turn the Director's :class:`CommentaryDirective`
decisions into spoken words. They share one pluggable provider interface:

- **Play-by-Play** — short, high-energy calls of live action (kills, entries,
  trades, plants, defuses, clutches).
- **Analyst** — longer, conversational read of economy, tendencies, the round
  narrative and replays.

Hard rules enforced here: use only the facts in the directive (never invent
names, numbers or outcomes), original wording, and never imitate any
identifiable real-world caster. The default provider is a deterministic template
engine that satisfies all three by construction; optional API-backed providers
enforce the same rules via their system prompt.
"""

from ai_caster.commentary.generator import CommentaryGenerator
from ai_caster.commentary.lines import CommentaryLine, CommentaryLineGenerated

__all__ = ["CommentaryGenerator", "CommentaryLine", "CommentaryLineGenerated"]
