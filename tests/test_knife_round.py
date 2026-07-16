"""Tests for knife-round detection and side-selection understanding."""

from __future__ import annotations

from ai_caster.detection.detectors import EventDetector, _best_of, is_knife_round
from ai_caster.detection.events import KnifeRound, MatchStarted
from ai_caster.director import policy
from ai_caster.director.policy import context_for_event, side_selection_note, topic_for_event
from ai_caster.gsi.models import GameState


def _knife_player(steamid: str, team: str, *, health: int = 100) -> dict:
    return {
        "name": f"p{steamid}",
        "team": team,
        "state": {"health": health, "equip_value": 0},
        "weapons": {"weapon_0": {"name": "weapon_knife", "type": "Knife", "state": "active"}},
    }


def _armed_player(steamid: str, team: str) -> dict:
    return {
        "name": f"p{steamid}",
        "team": team,
        "state": {"health": 100, "equip_value": 200},
        "weapons": {
            "w0": {"name": "weapon_glock", "type": "Pistol", "state": "active"},
            "w1": {"name": "weapon_knife", "type": "Knife", "state": "holstered"},
        },
    }


def _state(players: dict, *, phase: str = "live", to_win: int | None = None) -> dict:
    game_map: dict = {"name": "de_dust2", "phase": "live", "round": 0}
    if to_win is not None:
        game_map["num_matches_to_win_series"] = to_win
    return {
        "provider": {"name": "cs2", "appid": 730, "timestamp": 1000},
        "map": game_map,
        "round": {"phase": phase},
        "allplayers": players,
    }


# --- is_knife_round -------------------------------------------------------- #
def test_is_knife_round_true_when_all_players_hold_only_knives():
    players = {"1": _knife_player("1", "CT"), "2": _knife_player("2", "T")}
    assert is_knife_round(GameState.model_validate(_state(players)))


def test_is_knife_round_false_when_someone_has_a_gun():
    players = {"1": _knife_player("1", "CT"), "2": _armed_player("2", "T")}
    assert not is_knife_round(GameState.model_validate(_state(players)))


def test_is_knife_round_false_with_too_few_players():
    players = {"1": _knife_player("1", "CT")}
    assert not is_knife_round(GameState.model_validate(_state(players)))


# --- detector emits KnifeRound once ---------------------------------------- #
def test_detector_emits_knife_round_once():
    det = EventDetector()
    players = {"1": _knife_player("1", "CT"), "2": _knife_player("2", "T")}
    first = det.detect(GameState.model_validate(_state(players)))
    assert any(isinstance(e, KnifeRound) for e in first)
    # A second tick still in the knife round does not re-announce it.
    second = det.detect(GameState.model_validate(_state(players)))
    assert not any(isinstance(e, KnifeRound) for e in second)


def test_detector_no_knife_round_for_normal_buy():
    det = EventDetector()
    players = {"1": _armed_player("1", "CT"), "2": _armed_player("2", "T")}
    events = det.detect(GameState.model_validate(_state(players)))
    assert not any(isinstance(e, KnifeRound) for e in events)


# --- best-of / side selection ---------------------------------------------- #
def test_best_of_from_matches_to_win():
    assert _best_of(GameState.model_validate(_state({}, to_win=1))) == 1
    assert _best_of(GameState.model_validate(_state({}, to_win=2))) == 3
    assert _best_of(GameState.model_validate(_state({}, to_win=3))) == 5
    assert _best_of(GameState.model_validate(_state({}))) == 0


def test_side_selection_note_wording():
    assert "knife round decides" in side_selection_note(1)
    assert "didn't pick this map" in side_selection_note(3)
    assert "didn't pick this map" in side_selection_note(5)
    assert side_selection_note(0) == ""


def test_match_started_carries_best_of_and_side_note():
    det = EventDetector()
    players = {"1": _armed_player("1", "CT"), "2": _armed_player("2", "T")}
    events = det.detect(GameState.model_validate(_state(players, to_win=2)))
    started = next(e for e in events if isinstance(e, MatchStarted))
    assert started.best_of == 3
    ctx = context_for_event(started)
    assert ctx["best_of"] == 3
    assert "didn't pick this map" in ctx["side_selection"]


def test_knife_round_policy_topic_and_context():
    event = KnifeRound(round_number=0)
    assert topic_for_event(event) == "knife_round"
    assert policy.speaker_for_event(event).value == "analyst"
    ctx = context_for_event(event)
    assert "winner chooses which side" in ctx["side_rule"]
