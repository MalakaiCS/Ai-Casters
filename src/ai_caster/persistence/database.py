"""SQLite connection management and schema.

A thin wrapper over :mod:`sqlite3` that owns the connection, applies pragmatic
durability/concurrency settings, and creates the schema idempotently. A single
``schema_version`` row supports future migrations (M8+). Access is serialised
with a lock because the connection is shared across the network and UI threads.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from ai_caster.core.logging import get_logger

_log = get_logger("persistence.db")

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    map_name     TEXT,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    ct_name      TEXT,
    t_name       TEXT,
    ct_score     INTEGER DEFAULT 0,
    t_score      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rounds (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id      INTEGER NOT NULL REFERENCES matches(id),
    number        INTEGER NOT NULL,
    winner        TEXT,
    reason        TEXT,
    bomb_planted  INTEGER DEFAULT 0,
    UNIQUE(match_id, number)
);

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id      INTEGER NOT NULL REFERENCES matches(id),
    round_number  INTEGER NOT NULL,
    type          TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    data          TEXT
);

CREATE TABLE IF NOT EXISTS player_stats (
    match_id       INTEGER NOT NULL REFERENCES matches(id),
    steamid        TEXT NOT NULL,
    name           TEXT,
    side           TEXT,
    kills          INTEGER DEFAULT 0,
    deaths         INTEGER DEFAULT 0,
    assists        INTEGER DEFAULT 0,
    mvps           INTEGER DEFAULT 0,
    damage         INTEGER DEFAULT 0,
    headshots      INTEGER DEFAULT 0,
    rounds_played  INTEGER DEFAULT 0,
    opening_kills  INTEGER DEFAULT 0,
    clutches_won   INTEGER DEFAULT 0,
    PRIMARY KEY (match_id, steamid)
);

CREATE INDEX IF NOT EXISTS idx_events_match_round ON events(match_id, round_number);
"""


class Database:
    """Owns a single SQLite connection and the schema."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._lock = threading.RLock()
        # check_same_thread=False: we serialise access ourselves via the lock,
        # so the connection may be used from the network and UI threads.
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._configure()
        self._create_schema()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def _configure(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")

    def _create_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            row = self._conn.execute("SELECT version FROM schema_info LIMIT 1;").fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO schema_info(version) VALUES (?);", (SCHEMA_VERSION,)
                )
            self._conn.commit()
        _log.info("Database ready at %s (schema v%d)", self._path, SCHEMA_VERSION)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
