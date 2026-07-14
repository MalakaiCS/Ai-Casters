"""Tests for GSI payload parsing and the match state store."""

from __future__ import annotations

from ai_caster.gsi.models import GameState
from ai_caster.match.state import DataSource, MatchSnapshot, MatchStateStore
from tests.conftest import make_gsi_payload


def test_parses_representative_payload():
    state = GameState.model_validate(make_gsi_payload())
    assert state.map_name == "de_mirage"
    assert state.round_number == 4
    assert state.ct_score == 3
    assert state.t_score == 2
    assert state.observed_player_name == "s1mple_like_alias"
    assert state.round.bomb == "planted"


def test_unknown_fields_preserved():
    payload = make_gsi_payload()
    payload["map"]["some_future_field"] = "value"
    state = GameState.model_validate(payload)
    assert state.map.model_extra.get("some_future_field") == "value"


def test_partial_player_payload_parses():
    # Player-mode payload without allplayers/map should still parse.
    state = GameState.model_validate({"player": {"name": "x", "state": {"health": 50}}})
    assert state.observed_player_name == "x"
    assert state.map_name is None
    assert state.ct_score is None


def test_snapshot_counts_players_alive():
    state = GameState.model_validate(make_gsi_payload())
    snap = MatchSnapshot.from_game_state(state)
    # p1 health 100, p2 health 0, p3 health 45 -> 2 alive.
    assert snap.players_alive == 2
    assert snap.map_name == "de_mirage"


def test_store_latest_wins_for_equal_source():
    store = MatchStateStore()
    first = MatchSnapshot.from_game_state(GameState.model_validate(make_gsi_payload()))
    assert store.apply(first)
    payload = make_gsi_payload()
    payload["map"]["round"] = 10
    second = MatchSnapshot.from_game_state(GameState.model_validate(payload))
    assert store.apply(second)
    assert store.snapshot().round_number == 10


def test_store_rejects_weaker_stale_source():
    store = MatchStateStore()
    gsi_snap = MatchSnapshot.from_game_state(
        GameState.model_validate(make_gsi_payload()), source=DataSource.GSI
    )
    store.apply(gsi_snap)

    # A vision snapshot that is older must not clobber confirmed GSI data.
    vision_snap = MatchSnapshot(
        updated_at=gsi_snap.updated_at,  # not newer
        source=DataSource.VISION,
        map_name="de_vision_guess",
    )
    assert store.apply(vision_snap) is False
    assert store.snapshot().map_name == "de_mirage"
