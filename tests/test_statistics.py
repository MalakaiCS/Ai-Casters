"""Tests for the statistics engine."""

from __future__ import annotations

from ai_caster.detection.events import ClutchWon, Kill
from ai_caster.gsi.models import GameState
from ai_caster.match.model import build_live_match
from ai_caster.statistics.engine import StatisticsEngine
from tests.conftest import make_player, make_state


def _match(players):
    return build_live_match(GameState.model_validate(make_state(players)))


def test_sync_reads_authoritative_totals():
    engine = StatisticsEngine()
    engine.sync_from_match(
        _match([make_player("1", "a", "CT", kills=10, deaths=4, assists=2, mvps=1)])
    )
    stats = engine.statistics.player("1")
    assert stats.kills == 10
    assert stats.deaths == 4
    assert stats.kd_diff == 6
    assert round(stats.kd_ratio, 2) == 2.5


def test_opening_and_trade_kills_from_events():
    engine = StatisticsEngine()
    engine.record_event(Kill(killer_steamid="1", killer_name="a", is_entry=True))
    engine.record_event(Kill(killer_steamid="1", killer_name="a", is_trade=True))
    stats = engine.statistics.player("1")
    assert stats.opening_kills == 1
    assert stats.trade_kills == 1


def test_clutch_won_counted():
    engine = StatisticsEngine()
    engine.record_event(ClutchWon(player_steamid="7", player_name="clutcher"))
    assert engine.statistics.player("7").clutches_won == 1


def test_round_end_accumulates_damage_and_multikills():
    engine = StatisticsEngine()
    match = _match([make_player("1", "a", "CT", round_kills=3, round_totaldmg=280, round_killhs=2)])
    engine.record_round_end(match)
    stats = engine.statistics.player("1")
    assert stats.rounds_played == 1
    assert stats.damage == 280
    assert stats.headshots == 2
    assert stats.multikill_rounds[3] == 1
    assert stats.adr == 280.0


def test_adr_averages_over_rounds():
    engine = StatisticsEngine()
    for dmg in (100, 50):
        engine.record_round_end(_match([make_player("1", "a", "CT", round_totaldmg=dmg)]))
    assert engine.statistics.player("1").adr == 75.0


def test_top_fraggers_ordering():
    engine = StatisticsEngine()
    engine.sync_from_match(
        _match(
            [
                make_player("1", "low", "CT", kills=3),
                make_player("2", "high", "CT", kills=9),
            ]
        )
    )
    top = engine.statistics.top_fraggers(1)
    assert top[0].steamid == "2"


def test_reset_clears_stats():
    engine = StatisticsEngine()
    engine.sync_from_match(_match([make_player("1", "a", "CT", kills=5)]))
    engine.reset()
    assert engine.statistics.players == {}
