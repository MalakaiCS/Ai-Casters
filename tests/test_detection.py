"""Tests for the GSI-based event detector."""

from __future__ import annotations

from ai_caster.detection.detectors import EventDetector
from ai_caster.detection.events import (
    BombDefused,
    BombPlanted,
    ClutchStarted,
    ClutchWon,
    Kill,
    MatchStarted,
    PlayerDeath,
    RoundEnded,
    RoundStarted,
    ScoreChanged,
)
from ai_caster.gsi.models import GameState
from tests.conftest import make_player, make_state


def _detect(detector: EventDetector, payload: dict):
    return detector.detect(GameState.model_validate(payload))


def test_first_payload_emits_match_started():
    det = EventDetector()
    events = _detect(det, make_state([make_player("1", "a", "CT")], map_phase="live"))
    assert any(isinstance(e, MatchStarted) for e in events)


def test_kill_and_death_paired_when_unambiguous():
    det = EventDetector()
    players_before = [
        make_player("1", "killer", "CT", health=100, kills=0),
        make_player("2", "victim", "T", health=100, kills=0),
    ]
    _detect(det, make_state(players_before, provider_ts=1000))

    players_after = [
        make_player("1", "killer", "CT", health=100, kills=1, round_kills=1),
        make_player("2", "victim", "T", health=0, deaths=1),
    ]
    events = _detect(det, make_state(players_after, provider_ts=1001))

    kills = [e for e in events if isinstance(e, Kill)]
    deaths = [e for e in events if isinstance(e, PlayerDeath)]
    assert len(kills) == 1 and len(deaths) == 1
    assert kills[0].killer_steamid == "1"
    assert kills[0].victim_steamid == "2"  # paired
    assert kills[0].is_entry is True  # first blood of the round


def test_headshot_detected_from_round_killhs():
    det = EventDetector()
    _detect(
        det,
        make_state(
            [
                make_player("1", "k", "CT", kills=0, round_killhs=0),
                make_player("2", "v", "T", health=100),
            ],
            provider_ts=1000,
        ),
    )
    events = _detect(
        det,
        make_state(
            [
                make_player("1", "k", "CT", kills=1, round_kills=1, round_killhs=1),
                make_player("2", "v", "T", health=0, deaths=1),
            ],
            provider_ts=1001,
        ),
    )
    kill = next(e for e in events if isinstance(e, Kill))
    assert kill.headshot is True


def test_trade_kill_classified():
    det = EventDetector()
    # Tick 0: everyone alive.
    _detect(
        det,
        make_state(
            [
                make_player("1", "ct1", "CT", health=100),
                make_player("2", "ct2", "CT", health=100),
                make_player("3", "t1", "T", health=100, kills=0),
            ],
            provider_ts=1000,
        ),
    )
    # Tick 1: t1 kills ct1 (ct1 dies).
    _detect(
        det,
        make_state(
            [
                make_player("1", "ct1", "CT", health=0, deaths=1),
                make_player("2", "ct2", "CT", health=100, kills=0),
                make_player("3", "t1", "T", health=100, kills=1, round_kills=1),
            ],
            provider_ts=1001,
        ),
    )
    # Tick 2: ct2 kills t1 shortly after -> trade for CT.
    events = _detect(
        det,
        make_state(
            [
                make_player("1", "ct1", "CT", health=0, deaths=1),
                make_player("2", "ct2", "CT", health=100, kills=1, round_kills=1),
                make_player("3", "t1", "T", health=0, deaths=1),
            ],
            provider_ts=1002,
        ),
    )
    kill = next(e for e in events if isinstance(e, Kill) and e.killer_steamid == "2")
    assert kill.is_trade is True


def test_bomb_plant_and_defuse():
    det = EventDetector()
    base = [make_player("1", "a", "CT"), make_player("2", "b", "T")]
    _detect(det, make_state(base, bomb=None, provider_ts=1000))
    planted = _detect(det, make_state(base, bomb="planted", provider_ts=1001))
    defused = _detect(det, make_state(base, bomb="defused", provider_ts=1002))
    assert any(isinstance(e, BombPlanted) for e in planted)
    assert any(isinstance(e, BombDefused) for e in defused)


def test_round_start_and_end_and_score():
    det = EventDetector()
    players = [make_player("1", "a", "CT"), make_player("2", "b", "T")]
    # freezetime -> live triggers RoundStarted.
    _detect(det, make_state(players, round_phase="freezetime", provider_ts=1000))
    started = _detect(det, make_state(players, round_phase="live", provider_ts=1001))
    assert any(isinstance(e, RoundStarted) for e in started)
    # live -> over with a winner and score bump triggers RoundEnded + ScoreChanged.
    ended = _detect(
        det,
        make_state(players, round_phase="over", win_team="CT", ct_score=1, provider_ts=1002),
    )
    round_ended = next(e for e in ended if isinstance(e, RoundEnded))
    assert round_ended.winner == "CT"
    assert round_ended.reason == "elimination"
    assert any(isinstance(e, ScoreChanged) for e in ended)


def test_clutch_started_and_won():
    det = EventDetector()
    # Full 2v2 goes live -> no clutch yet.
    live = [
        make_player("1", "ct1", "CT", health=100),
        make_player("2", "ct2", "CT", health=100),
        make_player("3", "t1", "T", health=100),
        make_player("4", "t2", "T", health=100),
    ]
    _detect(det, make_state(live, round_phase="freezetime", provider_ts=1000))
    started = _detect(det, make_state(live, round_phase="live", provider_ts=1001))
    assert not any(isinstance(e, ClutchStarted) for e in started)

    # ct2 dies -> ct1 alone (1) vs two live T -> clutch.
    clutch_state = [
        make_player("1", "ct1", "CT", health=40),
        make_player("2", "ct2", "CT", health=0, deaths=1),
        make_player("3", "t1", "T", health=100),
        make_player("4", "t2", "T", health=100),
    ]
    events = _detect(det, make_state(clutch_state, round_phase="live", provider_ts=1002))
    clutch = next(e for e in events if isinstance(e, ClutchStarted))
    assert clutch.player_steamid == "1"
    assert clutch.opponents_alive == 2

    # CT wins the round -> clutch won.
    won = _detect(
        det,
        make_state(clutch_state, round_phase="over", win_team="CT", ct_score=1, provider_ts=1003),
    )
    clutch_won = next(e for e in won if isinstance(e, ClutchWon))
    assert clutch_won.player_steamid == "1"
    assert clutch_won.opponents_beaten == 2


def test_no_duplicate_match_started():
    det = EventDetector()
    s = make_state([make_player("1", "a", "CT")], map_phase="live")
    first = _detect(det, s)
    second = _detect(
        det, make_state([make_player("1", "a", "CT")], map_phase="live", provider_ts=1002)
    )
    assert sum(isinstance(e, MatchStarted) for e in first) == 1
    assert sum(isinstance(e, MatchStarted) for e in second) == 0
