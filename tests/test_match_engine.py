"""Integration tests for the Match State Engine (headless)."""

from __future__ import annotations

from ai_caster.core.events import EventBus, GSIStateUpdated
from ai_caster.detection.events import MatchEvent
from ai_caster.gsi.models import GameState
from ai_caster.match.engine import MatchStateEngine
from ai_caster.match.events import MatchModelUpdated
from ai_caster.persistence.database import Database
from ai_caster.persistence.repository import MatchRepository
from ai_caster.statistics.engine import StatisticsEngine
from tests.conftest import make_player, make_state


def _engine(repository=None, persist=False):
    bus = EventBus()
    published: list = []
    bus.subscribe(MatchModelUpdated, published.append)
    bus.subscribe(MatchEvent, published.append)
    engine = MatchStateEngine(bus, StatisticsEngine(), repository=repository, persist=persist)
    return bus, engine, published


def _push(bus: EventBus, payload: dict) -> None:
    bus.publish(GSIStateUpdated(game_state=GameState.model_validate(payload)))


def test_engine_builds_model_and_publishes_on_gsi_event():
    bus, engine, published = _engine()
    _push(bus, make_state([make_player("1", "a", "CT", kills=3)], round_no=2, ct_score=1))

    assert engine.live_match is not None
    assert engine.live_match.round_number == 2
    assert engine.live_match.ct.score == 1
    # A MatchModelUpdated was published.
    assert any(isinstance(e, MatchModelUpdated) for e in published)


def test_engine_accumulates_history_and_stats_on_round_end():
    bus, engine, _ = _engine()
    players = [make_player("1", "a", "CT", round_totaldmg=150), make_player("2", "b", "T")]
    _push(bus, make_state(players, round_phase="freezetime", provider_ts=1000))
    _push(bus, make_state(players, round_phase="live", provider_ts=1001))
    _push(
        bus,
        make_state(players, round_phase="over", win_team="CT", ct_score=1, provider_ts=1002),
    )

    assert len(engine.live_match.history) == 1
    assert engine.live_match.history[0].winner.value == "CT"
    # Momentum now reflects the CT round win.
    assert engine.live_match.momentum.value > 0
    # Round-end folded damage into stats.
    assert engine.statistics.statistics.player("1").damage == 150


def test_engine_returns_detected_events():
    bus, engine, _ = _engine()
    events = engine.on_gsi_update(
        GameState.model_validate(make_state([make_player("1", "a", "CT")], map_phase="live"))
    )
    assert any(isinstance(e, MatchEvent) for e in events)


def test_engine_persists_when_repository_configured(tmp_path):
    db = Database(tmp_path / "engine.sqlite")
    repo = MatchRepository(db)
    bus, engine, _ = _engine(repository=repo, persist=True)

    players = [make_player("1", "a", "CT"), make_player("2", "b", "T")]
    _push(bus, make_state(players, round_phase="freezetime", provider_ts=1000))
    _push(bus, make_state(players, round_phase="live", provider_ts=1001))
    _push(bus, make_state(players, round_phase="over", win_team="CT", ct_score=1, provider_ts=1002))

    assert engine.match_id is not None
    assert repo.count_rounds(engine.match_id) == 1
    # RoundStarted / RoundEnded / ScoreChanged etc. were stored.
    assert repo.count_events(engine.match_id) >= 2
    db.close()


def test_engine_resets_on_map_change():
    bus, engine, _ = _engine()
    _push(bus, make_state([make_player("1", "a", "CT")], map_name="de_mirage", ct_score=5))
    _push(bus, make_state([make_player("1", "a", "CT")], map_name="de_nuke", ct_score=0))
    assert engine.live_match.map_name == "de_nuke"
    assert engine.live_match.history == ()
