"""Tests for the SQLite persistence layer."""

from __future__ import annotations

from ai_caster.detection.events import BombPlanted, Kill
from ai_caster.match.model import RoundEndReason, RoundRecord, Side
from ai_caster.persistence.database import Database
from ai_caster.persistence.repository import MatchRepository
from ai_caster.statistics.models import MatchStatistics


def _repo(tmp_path) -> MatchRepository:
    db = Database(tmp_path / "test.sqlite")
    return MatchRepository(db)


def test_schema_created_and_match_roundtrip(tmp_path):
    repo = _repo(tmp_path)
    match_id = repo.start_match("de_inferno", "Astralis", "NAVI")
    match = repo.get_match(match_id)
    assert match["map_name"] == "de_inferno"
    assert match["ct_name"] == "Astralis"
    assert match["ended_at"] is None

    repo.finish_match(match_id, 13, 9)
    match = repo.get_match(match_id)
    assert match["ct_score"] == 13
    assert match["ended_at"] is not None


def test_record_round_is_idempotent(tmp_path):
    repo = _repo(tmp_path)
    match_id = repo.start_match("de_nuke")
    record = RoundRecord(
        number=1, winner=Side.CT, reason=RoundEndReason.BOMB_DEFUSED, bomb_planted=True
    )
    repo.record_round(match_id, record)
    repo.record_round(match_id, record)  # upsert, not duplicate
    assert repo.count_rounds(match_id) == 1


def test_record_events(tmp_path):
    repo = _repo(tmp_path)
    match_id = repo.start_match("de_vertigo")
    repo.record_event(match_id, Kill(round_number=1, killer_steamid="1", killer_name="a"))
    repo.record_event(match_id, BombPlanted(round_number=1))
    assert repo.count_events(match_id) == 2
    assert repo.count_events(match_id, "Kill") == 1


def test_save_and_read_statistics(tmp_path):
    repo = _repo(tmp_path)
    match_id = repo.start_match("de_ancient")
    stats = MatchStatistics()
    p = stats.player("1", "star", "CT")
    p.kills, p.deaths, p.damage, p.opening_kills = 20, 10, 2500, 4
    repo.save_statistics(match_id, stats)

    # Update and re-save -> upsert.
    p.kills = 25
    repo.save_statistics(match_id, stats)

    rows = repo.get_statistics(match_id)
    assert len(rows) == 1
    assert rows[0]["kills"] == 25
    assert rows[0]["opening_kills"] == 4
