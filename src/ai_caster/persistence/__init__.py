"""SQLite persistence for matches, rounds, events and player statistics.

Development uses SQLite (per the spec); the repository interface is written so a
PostgreSQL-backed implementation can be dropped in later without touching call
sites.
"""

from ai_caster.persistence.database import Database
from ai_caster.persistence.repository import MatchRepository

__all__ = ["Database", "MatchRepository"]
