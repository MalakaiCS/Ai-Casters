"""Module 9 (GSI portion) — Event Detection.

Detects match events by diffing consecutive GSI states: kills, deaths, entries,
trades, bomb plants/defuses/explosions, round starts/ends, clutches, score and
match-phase changes. Vision-based detection (kill feed, spray transfers, flick
shots) is added in Milestone 4 and fused on top with higher-fidelity data.
"""

from ai_caster.detection.detectors import EventDetector
from ai_caster.detection.events import (
    BombDefused,
    BombExploded,
    BombPlanted,
    ClutchStarted,
    ClutchWon,
    Kill,
    MatchEnded,
    MatchEvent,
    MatchStarted,
    PlayerDeath,
    RoundEnded,
    RoundStarted,
    ScoreChanged,
)

__all__ = [
    "EventDetector",
    "MatchEvent",
    "Kill",
    "PlayerDeath",
    "BombPlanted",
    "BombDefused",
    "BombExploded",
    "RoundStarted",
    "RoundEnded",
    "ClutchStarted",
    "ClutchWon",
    "MatchStarted",
    "MatchEnded",
    "ScoreChanged",
]
