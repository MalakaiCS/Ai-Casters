"""Detected match events.

These subclass the core :class:`~ai_caster.core.events.Event` so they can be
published on the same :class:`~ai_caster.core.events.EventBus` and routed to any
subscriber (UI, the future Commentary Director in M5, statistics). Keeping them
in the detection module — rather than in :mod:`core` — preserves the rule that
``core`` never imports feature concepts.

Each event carries the ``round_number`` it occurred in and, where meaningful, a
``confidence`` in ``[0, 1]`` so later vision fusion can express uncertainty. GSI
facts (bomb, score, phase) are confirmed and default to ``1.0``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_caster.core.events import Event


@dataclass(frozen=True)
class MatchEvent(Event):
    """Base class for everything the detector emits."""

    round_number: int = 0
    confidence: float = 1.0


@dataclass(frozen=True)
class MatchStarted(MatchEvent):
    map_name: str | None = None


@dataclass(frozen=True)
class MatchEnded(MatchEvent):
    winner: str | None = None  # "CT" / "T"
    ct_score: int = 0
    t_score: int = 0


@dataclass(frozen=True)
class RoundStarted(MatchEvent):
    pass


@dataclass(frozen=True)
class RoundEnded(MatchEvent):
    winner: str | None = None  # "CT" / "T"
    reason: str = "unknown"
    bomb_planted: bool = False


@dataclass(frozen=True)
class ScoreChanged(MatchEvent):
    ct_score: int = 0
    t_score: int = 0


@dataclass(frozen=True)
class PlayerDeath(MatchEvent):
    victim_steamid: str = ""
    victim_name: str = ""
    victim_side: str | None = None


@dataclass(frozen=True)
class Kill(MatchEvent):
    """A kill credited to ``killer``.

    GSI does not directly link killer to victim, so ``victim_*`` is filled only
    when the diff is unambiguous (exactly one death paired with one kill in the
    same tick). Vision (M4) will supply reliable pairing and weapon/headshot
    detail.
    """

    killer_steamid: str = ""
    killer_name: str = ""
    killer_side: str | None = None
    victim_steamid: str | None = None
    victim_name: str | None = None
    weapon: str | None = None
    headshot: bool = False
    is_entry: bool = False
    is_trade: bool = False


@dataclass(frozen=True)
class BombPlanted(MatchEvent):
    pass


@dataclass(frozen=True)
class BombDefused(MatchEvent):
    pass


@dataclass(frozen=True)
class BombExploded(MatchEvent):
    pass


@dataclass(frozen=True)
class ClutchStarted(MatchEvent):
    """A single surviving player faces two or more live opponents."""

    player_steamid: str = ""
    player_name: str = ""
    player_side: str | None = None
    opponents_alive: int = 0


@dataclass(frozen=True)
class ClutchWon(MatchEvent):
    player_steamid: str = ""
    player_name: str = ""
    player_side: str | None = None
    opponents_beaten: int = 0
