"""Module 17 — Statistics Engine.

Accumulates per-player and per-team statistics across a match from the
authoritative GSI match-stats snapshot plus detected events (opening kills,
clutches, multi-kills, damage). Consumed by the analyst commentary (M6) and the
UI.
"""

from ai_caster.statistics.engine import StatisticsEngine
from ai_caster.statistics.models import MatchStatistics, PlayerStats

__all__ = ["StatisticsEngine", "MatchStatistics", "PlayerStats"]
