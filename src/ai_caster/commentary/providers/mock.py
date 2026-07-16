"""Deterministic template provider — the default commentary backend.

Generates believable, varied commentary purely from the directive's structured
facts, with no network and no API key. Because it only ever substitutes values
that came from the match itself, it **cannot invent facts**, and its wording is
generic (never imitating any real caster) — satisfying the project's hard rules
by construction. It is also what makes the whole commentary path unit-testable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ai_caster.commentary.providers.base import LLMRequest


def _variant(options: list[str], context: dict[str, Any]) -> str:
    """Pick a variant deterministically from the round number."""
    if not options:
        return ""
    index = int(context.get("round", 0)) % len(options)
    return options[index]


def _kill(ctx: dict[str, Any]) -> str:
    killer = ctx.get("killer") or "the attacker"
    victim = ctx.get("victim")
    if victim:
        line = _variant(
            [
                f"{killer} drops {victim}!",
                f"{killer} takes down {victim}!",
                f"{killer} cracks {victim}!",
            ],
            ctx,
        )
    else:
        line = _variant([f"{killer} gets the frag!", f"{killer} finds a kill!"], ctx)
    if ctx.get("entry"):
        line = f"Opening pick — {line}"
    if ctx.get("headshot"):
        line = f"{line} Straight through the head."
    elif ctx.get("trade"):
        line = f"{line} The trade comes instantly."
    return line


def _clutch_started(ctx: dict[str, Any]) -> str:
    player = ctx.get("player") or "the survivor"
    opp = ctx.get("opponents", 0)
    return (
        f"{player} is the last one alive — {opp_word(opp)} to handle!"
        if opp
        else f"{player} stands alone!"
    )


def _clutch_won(ctx: dict[str, Any]) -> str:
    player = ctx.get("player") or "the survivor"
    opp = ctx.get("opponents", 0)
    return f"{player} WINS the clutch — {opp_word(opp)} taken down single-handed!"


def opp_word(n: int) -> str:
    return f"{n} opponents" if n != 1 else "one opponent"


def _round_ended(ctx: dict[str, Any]) -> str:
    winner = ctx.get("winner") or "the round"
    reason = ctx.get("reason", "")
    tail = {
        "bomb_exploded": " The bomb does the talking.",
        "bomb_defused": " Defused with time to spare.",
        "elimination": " A clean sweep.",
    }.get(reason, "")
    return f"Round goes to the {winner} side.{tail}"


_BUILDERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "Kill": _kill,
    "ClutchStarted": _clutch_started,
    "ClutchWon": _clutch_won,
    "RoundEnded": _round_ended,
    "BombPlanted": lambda _c: "The bomb is down — the clock is ticking.",
    "BombDefused": lambda _c: "Defused! The CTs snatch it back.",
    "BombExploded": lambda _c: "Boom — the site goes up.",
    "RoundStarted": lambda _c: "Fresh round underway. Let's see the setups.",
    "MatchStarted": lambda c: f"We are live on {c.get('map') or 'this map'}. Here we go.",
    "MatchEnded": lambda c: (
        f"That's the match — the {c.get('winner') or 'winning'} side take it "
        f"{c.get('ct_score', 0)} to {c.get('t_score', 0)}."
    ),
    "round_analysis": lambda c: (
        f"Let's break that one down — the {c.get('winner') or 'winning'} side read it perfectly."
    ),
    "replay": lambda c: f"Here's another look at that {c.get('replay_type', 'moment')}.",
    "back_to_live": lambda _c: "And we're back to the live action.",
    # -- downtime / desk chatter (timeouts, pauses, breaks) ------------- #
    "timeout_expectation": lambda c: (
        f"{c.get('team') or 'That side'} have called this timeout at {c.get('score', '0-0')} — "
        "expect them to settle the nerves, reset the economy and come back with a fresh plan."
    ),
    "downtime_stat": lambda c: (
        f"While we've got a moment — we're {c.get('score', '0-0')} through "
        f"{c.get('round', 0)} rounds here on {c.get('map') or 'this map'}."
    ),
    "halftime_recap": lambda c: (
        f"Time to take stock at {c.get('score', '0-0')} — plenty for both benches to talk through."
    ),
    "downtime_chatter": lambda _c: (
        "A bit of a breather here — good chance for both teams to regroup and look ahead."
    ),
    "warmup_preview": lambda c: (
        f"Still in the warm-up on {c.get('map') or 'this map'} — plenty to look forward to "
        "once we go live."
    ),
}


class MockProvider:
    """Template-based, deterministic, offline commentary."""

    name = "mock"

    def generate(self, request: LLMRequest) -> str:
        builder = _BUILDERS.get(request.topic)
        if builder is not None:
            return builder(request.context)
        # Unknown topic -> a safe, generic acknowledgement (no invented facts).
        return "A big moment here in the server."
