"""Statistics data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlayerStats:
    """Accumulated statistics for one player across the current match.

    Cumulative fields (kills/deaths/assists/mvps/score) mirror the authoritative
    GSI match-stats snapshot; derived fields (opening kills, clutches, damage,
    multi-kills, headshots) are accumulated from detected events and per-round
    snapshots.
    """

    steamid: str
    name: str = ""
    side: str | None = None

    kills: int = 0
    deaths: int = 0
    assists: int = 0
    mvps: int = 0
    score: int = 0

    headshots: int = 0
    damage: int = 0
    rounds_played: int = 0
    opening_kills: int = 0
    trade_kills: int = 0
    clutches_won: int = 0
    # Multi-kill round counts indexed 1..5 (index 0 unused).
    multikill_rounds: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0])

    @property
    def kd_ratio(self) -> float:
        return self.kills / self.deaths if self.deaths else float(self.kills)

    @property
    def kd_diff(self) -> int:
        return self.kills - self.deaths

    @property
    def adr(self) -> float:
        """Average damage per round."""
        return round(self.damage / self.rounds_played, 1) if self.rounds_played else 0.0

    @property
    def headshot_pct(self) -> float:
        return round(100 * self.headshots / self.kills, 1) if self.kills else 0.0


@dataclass
class TeamStats:
    """Team-level rollups derived from its players."""

    side: str
    name: str = ""
    kills: int = 0
    deaths: int = 0
    damage: int = 0


@dataclass
class MatchStatistics:
    """Container of per-player stats for a match, with convenience rollups."""

    players: dict[str, PlayerStats] = field(default_factory=dict)

    def player(self, steamid: str, name: str = "", side: str | None = None) -> PlayerStats:
        """Get or create the stats record for a player."""
        stats = self.players.get(steamid)
        if stats is None:
            stats = PlayerStats(steamid=steamid, name=name, side=side)
            self.players[steamid] = stats
        if name:
            stats.name = name
        if side is not None:
            stats.side = side
        return stats

    def top_fraggers(self, limit: int = 5) -> list[PlayerStats]:
        return sorted(self.players.values(), key=lambda p: (p.kills, p.kd_diff), reverse=True)[
            :limit
        ]

    def team_stats(self) -> dict[str, TeamStats]:
        teams: dict[str, TeamStats] = {}
        for stats in self.players.values():
            if stats.side not in {"CT", "T"}:
                continue
            team = teams.setdefault(stats.side, TeamStats(side=stats.side))
            team.kills += stats.kills
            team.deaths += stats.deaths
            team.damage += stats.damage
        return teams
