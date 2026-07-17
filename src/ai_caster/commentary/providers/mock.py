"""Deterministic template provider — the default commentary backend.

Generates believable, varied commentary purely from the directive's structured
facts, with no network and no API key. Because it only ever substitutes values
that came from the match itself, it **cannot invent facts**, and its wording is
generic (never imitating any real caster) — satisfying the project's hard rules
by construction. It is also what makes the whole commentary path unit-testable.

Every topic offers a *pool* of phrasings and the provider rotates through the
pool per topic, so the same situation (a bomb plant, a slow round, a timeout)
does not produce the same sentence twice in a row — the number-one complaint
about template casters. The rotation is per-instance and call-ordered, so output
is still deterministic given a call sequence (the tests rely on that), but a real
broadcast hears variety.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from ai_caster.commentary.providers.base import LLMRequest


def _kill(ctx: dict[str, Any]) -> list[str]:
    killer = ctx.get("killer") or "the attacker"
    victim = ctx.get("victim")
    if victim:
        return [
            f"{killer} drops {victim}!",
            f"{killer} takes down {victim}!",
            f"{killer} cracks {victim}!",
            f"{killer} puts away {victim}!",
            f"{killer} deletes {victim}!",
            f"{killer} finds {victim}!",
        ]
    return [
        f"{killer} gets the frag!",
        f"{killer} finds a kill!",
        f"{killer} picks one off!",
        f"{killer} adds another!",
    ]


def _decorate_kill(line: str, ctx: dict[str, Any]) -> str:
    if ctx.get("entry"):
        line = f"Opening pick — {line}"
    if ctx.get("headshot"):
        line = f"{line} Straight through the head."
    elif ctx.get("trade"):
        line = f"{line} The trade comes instantly."
    return line


def _clutch_started(ctx: dict[str, Any]) -> list[str]:
    player = ctx.get("player") or "the survivor"
    opp = ctx.get("opponents", 0)
    if opp:
        word = opp_word(opp)
        return [
            f"{player} is the last one alive — {word} to handle!",
            f"It's all on {player} now — {word} left standing!",
            f"{player} stands between the round and defeat — {word} to deal with!",
        ]
    return [f"{player} stands alone!", f"It's down to {player}!"]


def _clutch_won(ctx: dict[str, Any]) -> list[str]:
    player = ctx.get("player") or "the survivor"
    opp = ctx.get("opponents", 0)
    word = opp_word(opp)
    return [
        f"{player} WINS the clutch — {word} taken down single-handed!",
        f"{player} pulls it off — {word} down, round won alone!",
        f"Unbelievable from {player} — the clutch is good, {word} handled!",
    ]


def opp_word(n: int) -> str:
    return f"{n} opponents" if n != 1 else "one opponent"


def _winner_word(ctx: dict[str, Any]) -> tuple[str, bool]:
    """The winner's name and whether it's a real team name (vs a CT/T side label)."""
    team = ctx.get("winner_team")
    if team and team not in ("CT", "T"):
        return team, True
    return (ctx.get("winner") or "winning"), False


def _round_ended(ctx: dict[str, Any]) -> list[str]:
    who, named = _winner_word(ctx)
    reason = ctx.get("reason", "")
    tail = {
        "bomb_exploded": " The bomb does the talking.",
        "bomb_defused": " Defused with time to spare.",
        "elimination": " A clean sweep.",
    }.get(reason, "")
    if named:
        return [
            f"Round goes to {who}.{tail}",
            f"That one's for {who}.{tail}",
            f"{who} bank it.{tail}",
        ]
    return [
        f"Round goes to the {who} side.{tail}",
        f"That one's for the {who} side.{tail}",
        f"The {who} side bank it.{tail}",
    ]


def _timeout_expectation(ctx: dict[str, Any]) -> list[str]:
    team = ctx.get("team") or "That side"
    score = ctx.get("score", "0-0")
    return [
        f"{team} have called this timeout at {score} — expect them to settle the nerves, "
        "reset the economy and come back with a fresh plan.",
        f"{team} stop the clock at {score}; look for them to re-draw their defaults and "
        "take the pace out of the game for a round or two.",
        f"A timeout from {team} at {score} — a chance to break the opponent's rhythm and "
        "regroup around a set play out of the pause.",
    ]


def _downtime_stat(ctx: dict[str, Any]) -> list[str]:
    score = ctx.get("score", "0-0")
    rounds = ctx.get("round", 0)
    map_name = ctx.get("map") or "this map"
    return [
        f"While we've got a moment — we're {score} through {rounds} rounds here on {map_name}.",
        f"Quick check of the board: {score} after {rounds} rounds on {map_name}.",
        f"Sitting at {score} on {map_name}, {rounds} rounds in — plenty of game still to play.",
    ]


def _halftime_recap(ctx: dict[str, Any]) -> list[str]:
    score = ctx.get("score", "0-0")
    return [
        f"Time to take stock at {score} — plenty for both benches to talk through.",
        f"A breather at {score}; both coaches will be busy on the whiteboard.",
        f"We pause at {score} — a good spot to reset and look at what's working.",
    ]


def _slow_round_stat(ctx: dict[str, Any]) -> list[str]:
    score = ctx.get("score", "0-0")
    rounds = ctx.get("round", 0)
    map_name = ctx.get("map") or "this map"
    leader = ctx.get("momentum_leader")
    lines = [
        f"Patient stuff here — {score} on {map_name}, both sides playing for information.",
        f"No rush from either team; we're {score} deep into round {rounds} on {map_name}.",
        f"A slow, methodical round taking shape at {score}.",
    ]
    if leader:
        lines.append(f"The {leader} side carry the momentum into this one at {score}.")
    return lines


def _ct_label(ctx: dict[str, Any]) -> str:
    team = ctx.get("ct_team")
    return team if team and team not in ("CT", "T") else "the CTs"


def _t_label(ctx: dict[str, Any]) -> str:
    team = ctx.get("t_team")
    return team if team and team not in ("CT", "T") else "the Ts"


def _slow_round_economy(ctx: dict[str, Any]) -> list[str]:
    ct_buy = ctx.get("ct_buy") or "unknown"
    t_buy = ctx.get("t_buy") or "unknown"
    ct, t = _ct_label(ctx), _t_label(ctx)
    return [
        f"Economy-wise it's a {ct_buy} for {ct} against a {t_buy} from {t} — "
        "that shapes how aggressive either side can afford to be.",
        f"With {ct} on a {ct_buy} and {t} on a {t_buy}, both weigh every duel this round.",
        f"A {ct_buy} against a {t_buy} — the money's dictating the tempo here.",
    ]


def _slow_round_positioning(ctx: dict[str, Any]) -> list[str]:
    map_name = ctx.get("map") or "this map"
    area = ctx.get("area") or "the key areas"
    ct, t = _ct_label(ctx), _t_label(ctx)
    ct_alive = ctx.get("ct_alive")
    t_alive = ctx.get("t_alive")
    lines = [
        f"Still a lot of this round about {area} — territory won there decides how it opens up.",
        f"{t} feeling out the space, {ct} looking for the pick that breaks it open.",
        f"Utility held back for now; expect a committed hit once someone reads {area}.",
    ]
    if ct_alive is not None and t_alive is not None:
        lines.append(
            f"Still {ct_alive} on {t_alive} with no contact — a real war of patience on {map_name}."
        )
    return lines


def _map_control(ctx: dict[str, Any]) -> list[str]:
    map_name = ctx.get("map") or "this map"
    area = ctx.get("area") or "the middle"
    ct, t = _ct_label(ctx), _t_label(ctx)
    return [
        f"Early doors on {map_name}, it's all about {area} — {t} will want that space "
        f"and {ct} won't give it cheaply.",
        f"Watch the fight for {area} to open the round; whoever wins it sets the tempo.",
        f"{t} looking to test {area} early, chipping at {ct} to force a read — "
        "control there shapes the whole round.",
        f"This opening is about map control through {area}; expect the utility to start flying.",
    ]


def _late_round(ctx: dict[str, Any]) -> list[str]:
    seconds = ctx.get("seconds")
    t = _t_label(ctx)
    clock = f"{seconds}s" if seconds is not None else "not long"
    return [
        f"Clock's a factor now — {clock} left and {t} have to commit.",
        f"Down to {clock} on the round; time pressure squarely on {t}.",
        f"{t} running out of round here — {clock} to make something happen.",
    ]


def _match_started(ctx: dict[str, Any]) -> list[str]:
    map_name = ctx.get("map") or "this map"
    best_of = ctx.get("best_of") or 0
    side = ctx.get("side_selection")
    lines = [
        f"We are live on {map_name}. Here we go.",
        f"Underway on {map_name} — let's get into it.",
    ]
    if best_of in (1, 3, 5):
        lines.append(f"Best-of-{best_of} on {map_name}; {side}." if side else f"Best-of-{best_of}.")
    if side:
        lines.append(f"Worth remembering — {side} here on {map_name}.")
    return lines


def _knife_round(ctx: dict[str, Any]) -> list[str]:
    rule = ctx.get("side_rule") or "the winner chooses which side to start on"
    return [
        f"Knife round first — {rule}, so this matters more than it looks.",
        f"It's the knife round: {rule}. Every duel counts.",
        f"Sides on the line in the knife round — {rule}.",
    ]


_BUILDERS: dict[str, Callable[[dict[str, Any]], list[str]]] = {
    "Kill": _kill,
    "ClutchStarted": _clutch_started,
    "ClutchWon": _clutch_won,
    "RoundEnded": _round_ended,
    "BombPlanted": lambda _c: [
        "The bomb is down — the clock is ticking.",
        "Bomb goes down; the round is on a timer now.",
        "It's planted — CTs have to retake or lose it.",
    ],
    "BombDefused": lambda _c: [
        "Defused! The CTs snatch it back.",
        "Cut the wire — the defuse is good!",
        "Defused with the round on the line!",
    ],
    "BombExploded": lambda _c: [
        "Boom — the site goes up.",
        "The bomb detonates; that's the round.",
        "Up it goes — nothing the CTs could do.",
    ],
    "RoundStarted": lambda _c: [
        "Fresh round underway. Let's see the setups.",
        "Here's the next one — watch the defaults.",
        "New round, clean slate; positions being taken.",
    ],
    "MatchStarted": _match_started,
    "knife_round": _knife_round,
    "MatchEnded": lambda c: (
        [
            f"That's the match — {_winner_word(c)[0]} take it "
            f"{c.get('ct_score', 0)} to {c.get('t_score', 0)}.",
            f"It's all over: {_winner_word(c)[0]} close it out "
            f"{c.get('ct_score', 0)}-{c.get('t_score', 0)}.",
        ]
        if _winner_word(c)[1]
        else [
            f"That's the match — the {_winner_word(c)[0]} side take it "
            f"{c.get('ct_score', 0)} to {c.get('t_score', 0)}.",
            f"It's all over: the {_winner_word(c)[0]} side close it out "
            f"{c.get('ct_score', 0)}-{c.get('t_score', 0)}.",
        ]
    ),
    "round_analysis": lambda c: (
        [
            f"Let's break that one down — {_winner_word(c)[0]} read it perfectly.",
            f"Rewinding that round: {_winner_word(c)[0]} made the right call.",
        ]
        if _winner_word(c)[1]
        else [
            f"Let's break that one down — the {_winner_word(c)[0]} side read it perfectly.",
            f"Rewinding that round: the {_winner_word(c)[0]} side made the right call.",
        ]
    ),
    "replay": lambda c: [
        f"Here's another look at that {c.get('replay_type', 'moment')}.",
        f"Take another look at the {c.get('replay_type', 'moment')} here.",
    ],
    "back_to_live": lambda _c: [
        "And we're back to the live action.",
        "Back to live — let's pick it up.",
    ],
    # -- co-caster reaction (a live banter beat after a huge play) ------ #
    "reaction": lambda _c: [
        "That's exactly what I mean — ice in the veins there.",
        "Unreal composure; you don't see that under pressure.",
        "And that's the round on its head — huge from them.",
        "Textbook execution when it mattered most.",
    ],
    # -- downtime / desk chatter (timeouts, pauses, breaks) ------------- #
    "timeout_expectation": _timeout_expectation,
    "downtime_stat": _downtime_stat,
    "halftime_recap": _halftime_recap,
    "downtime_chatter": lambda _c: [
        "A bit of a breather here — good chance for both teams to regroup and look ahead.",
        "Quiet moment on the desk; time to look at the bigger picture.",
    ],
    "warmup_preview": lambda c: [
        (
            f"Still in the warm-up on {c.get('map') or 'this map'} — plenty to look forward to "
            "once we go live."
        ),
        f"Warm-up rolling on {c.get('map') or 'this map'}; not long until the real thing.",
    ],
    # -- slow / methodical live rounds (quiet-live filler) -------------- #
    "slow_round_stat": _slow_round_stat,
    "slow_round_economy": _slow_round_economy,
    "slow_round_positioning": _slow_round_positioning,
    # -- round stages: opening map control + late-round time pressure ---- #
    "map_control": _map_control,
    "late_round": _late_round,
}


# Topics where a spoken lead-in ("Right —") reads as the analyst answering the
# play-by-play, so the offline desk shows banter too (no facts invented).
_REACTIVE_TOPICS = frozenset(
    {"reaction", "round_analysis", "halftime_recap", "slow_round_positioning"}
)
_CONNECTIVES = ("Right —", "Exactly —", "And on that,", "Building on that,")


class MockProvider:
    """Template-based, offline commentary that rotates phrasings to avoid repeats."""

    name = "mock"

    def __init__(self) -> None:
        # Per-topic rotation cursor so consecutive lines on the same topic differ.
        self._rotation: dict[str, int] = defaultdict(int)
        self._connective = 0

    def generate(self, request: LLMRequest) -> str:
        builder = _BUILDERS.get(request.topic)
        if builder is None:
            # Unknown topic -> a safe, generic acknowledgement (no invented facts).
            return "A big moment here in the server."
        options = builder(request.context)
        if not options:
            return "A big moment here in the server."
        index = self._rotation[request.topic] % len(options)
        self._rotation[request.topic] += 1
        line = options[index]
        if request.topic == "Kill":
            line = _decorate_kill(line, request.context)
        else:
            line = self._maybe_react(line, request)
        return line

    def _maybe_react(self, line: str, request: LLMRequest) -> str:
        """Prefix a light connective when answering the co-caster (offline banter)."""
        if request.topic not in _REACTIVE_TOPICS or not request.conversation:
            return line
        last_speaker = request.conversation[-1][0]
        if not request.speaker or last_speaker == request.speaker:
            return line  # co-caster didn't just speak; no reaction lead-in
        connective = _CONNECTIVES[self._connective % len(_CONNECTIVES)]
        self._connective += 1
        return f"{connective} {line[0].lower() + line[1:]}" if line else line
