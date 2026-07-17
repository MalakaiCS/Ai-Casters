"""The statistics engine.

Accumulates a :class:`MatchStatistics` from two inputs:

1. **Authoritative snapshots** — cumulative kills/deaths/assists/mvps/score are
   read straight from the GSI ``match_stats`` block via the live match model, so
   they always match the scoreboard.
2. **Detected events & round snapshots** — opening kills, trades, clutches,
   headshots, per-round damage and multi-kills are accumulated from the event
   stream and round-end snapshots, since GSI does not total these itself.

The engine is pure domain logic: it never touches the bus, UI or database. The
composition root wires it to the event stream and persistence.
"""

from __future__ import annotations

from ai_caster.core.logging import get_logger
from ai_caster.detection.events import ClutchWon, Kill, MatchEvent
from ai_caster.match.model import LiveMatch
from ai_caster.statistics.models import MatchStatistics

_log = get_logger("statistics")


class StatisticsEngine:
    """Builds and holds match statistics."""

    def __init__(self) -> None:
        self._stats = MatchStatistics()

    @property
    def statistics(self) -> MatchStatistics:
        return self._stats

    def reset(self) -> None:
        """Clear all statistics (new match/map)."""
        self._stats = MatchStatistics()

    # ------------------------------------------------------------------ #
    def sync_from_match(self, match: LiveMatch) -> None:
        """Refresh authoritative cumulative fields from the live match model."""
        for player in match.players:
            stats = self._stats.player(
                player.steamid, player.name, player.side.value if player.side else None
            )
            stats.kills = player.match_kills
            stats.deaths = player.match_deaths
            stats.assists = player.match_assists
            stats.mvps = player.match_mvps
            stats.score = player.match_score

    def record_event(self, event: MatchEvent) -> None:
        """Accumulate the event-derived statistics GSI does not total itself."""
        if isinstance(event, Kill):
            stats = self._stats.player(event.killer_steamid, event.killer_name, event.killer_side)
            if event.is_entry:
                stats.opening_kills += 1
            if event.is_trade:
                stats.trade_kills += 1
        elif isinstance(event, ClutchWon):
            stats = self._stats.player(event.player_steamid, event.player_name, event.player_side)
            stats.clutches_won += 1

    def record_round_end(self, match: LiveMatch) -> None:
        """At round end, fold per-round snapshot numbers into the totals.

        Per-round damage, headshots and kill counts come from each player's
        round snapshot in the model. Multi-kill rounds (2k–5k) are bucketed here.
        """
        for player in match.players:
            side = player.side.value if player.side else None
            stats = self._stats.player(player.steamid, player.name, side)
            stats.rounds_played += 1
            stats.damage += max(0, player.round_damage)
            stats.headshots += max(0, player.round_headshots)
            round_kills = max(0, min(player.round_kills, 5))
            if round_kills >= 1:
                stats.multikill_rounds[round_kills] += 1
