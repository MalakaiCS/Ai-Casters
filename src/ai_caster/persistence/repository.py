"""Repository for reading and writing match data.

All SQL lives here behind intention-revealing methods, so the rest of the app
never builds queries. Writes are parameterised (no string interpolation) and
serialised through the database lock.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime

from ai_caster.core.logging import get_logger
from ai_caster.detection.events import MatchEvent
from ai_caster.match.model import RoundRecord
from ai_caster.persistence.database import Database
from ai_caster.statistics.models import MatchStatistics

_log = get_logger("persistence.repo")


def _event_payload(event: MatchEvent) -> str:
    """Serialise the event's fields (minus bookkeeping) to JSON."""
    data = asdict(event) if is_dataclass(event) else {}
    data.pop("timestamp", None)
    data.pop("round_number", None)
    return json.dumps(data, default=str)


class MatchRepository:
    """CRUD for matches, rounds, events and player statistics."""

    def __init__(self, database: Database) -> None:
        self._db = database

    # ------------------------------------------------------------------ #
    # Matches
    # ------------------------------------------------------------------ #
    def start_match(self, map_name: str | None, ct_name: str = "", t_name: str = "") -> int:
        started_at = datetime.now(UTC).isoformat()
        with self._db.lock:
            cur = self._db.connection.execute(
                "INSERT INTO matches(map_name, started_at, ct_name, t_name) VALUES (?, ?, ?, ?);",
                (map_name, started_at, ct_name, t_name),
            )
            self._db.connection.commit()
            return int(cur.lastrowid)

    def finish_match(self, match_id: int, ct_score: int, t_score: int) -> None:
        ended_at = datetime.now(UTC).isoformat()
        with self._db.lock:
            self._db.connection.execute(
                "UPDATE matches SET ended_at=?, ct_score=?, t_score=? WHERE id=?;",
                (ended_at, ct_score, t_score, match_id),
            )
            self._db.connection.commit()

    def get_match(self, match_id: int) -> dict | None:
        with self._db.lock:
            row = self._db.connection.execute(
                "SELECT * FROM matches WHERE id=?;", (match_id,)
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------ #
    # Rounds
    # ------------------------------------------------------------------ #
    def record_round(self, match_id: int, record: RoundRecord) -> None:
        winner = record.winner.value if record.winner else None
        with self._db.lock:
            self._db.connection.execute(
                """INSERT INTO rounds(match_id, number, winner, reason, bomb_planted)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(match_id, number) DO UPDATE SET
                       winner=excluded.winner,
                       reason=excluded.reason,
                       bomb_planted=excluded.bomb_planted;""",
                (match_id, record.number, winner, record.reason.value, int(record.bomb_planted)),
            )
            self._db.connection.commit()

    def count_rounds(self, match_id: int) -> int:
        with self._db.lock:
            row = self._db.connection.execute(
                "SELECT COUNT(*) AS c FROM rounds WHERE match_id=?;", (match_id,)
            ).fetchone()
        return int(row["c"])

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #
    def record_event(self, match_id: int, event: MatchEvent) -> None:
        with self._db.lock:
            self._db.connection.execute(
                "INSERT INTO events(match_id, round_number, type, timestamp, data) "
                "VALUES (?, ?, ?, ?, ?);",
                (
                    match_id,
                    event.round_number,
                    type(event).__name__,
                    event.timestamp.isoformat(),
                    _event_payload(event),
                ),
            )
            self._db.connection.commit()

    def count_events(self, match_id: int, event_type: str | None = None) -> int:
        with self._db.lock:
            if event_type:
                row = self._db.connection.execute(
                    "SELECT COUNT(*) AS c FROM events WHERE match_id=? AND type=?;",
                    (match_id, event_type),
                ).fetchone()
            else:
                row = self._db.connection.execute(
                    "SELECT COUNT(*) AS c FROM events WHERE match_id=?;", (match_id,)
                ).fetchone()
        return int(row["c"])

    # ------------------------------------------------------------------ #
    # Player statistics
    # ------------------------------------------------------------------ #
    def save_statistics(self, match_id: int, statistics: MatchStatistics) -> None:
        rows = [
            (
                match_id,
                s.steamid,
                s.name,
                s.side,
                s.kills,
                s.deaths,
                s.assists,
                s.mvps,
                s.damage,
                s.headshots,
                s.rounds_played,
                s.opening_kills,
                s.clutches_won,
            )
            for s in statistics.players.values()
        ]
        if not rows:
            return
        with self._db.lock:
            self._db.connection.executemany(
                """INSERT INTO player_stats(
                       match_id, steamid, name, side, kills, deaths, assists, mvps,
                       damage, headshots, rounds_played, opening_kills, clutches_won)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(match_id, steamid) DO UPDATE SET
                       name=excluded.name, side=excluded.side, kills=excluded.kills,
                       deaths=excluded.deaths, assists=excluded.assists, mvps=excluded.mvps,
                       damage=excluded.damage, headshots=excluded.headshots,
                       rounds_played=excluded.rounds_played,
                       opening_kills=excluded.opening_kills,
                       clutches_won=excluded.clutches_won;""",
                rows,
            )
            self._db.connection.commit()

    def get_statistics(self, match_id: int) -> list[dict]:
        with self._db.lock:
            rows = self._db.connection.execute(
                "SELECT * FROM player_stats WHERE match_id=? ORDER BY kills DESC;",
                (match_id,),
            ).fetchall()
        return [dict(r) for r in rows]
