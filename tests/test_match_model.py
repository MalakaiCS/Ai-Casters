"""Tests for the live match model and its derived metrics."""

from __future__ import annotations

from ai_caster.gsi.models import GameState
from ai_caster.match.model import (
    BuyType,
    Momentum,
    RoundEndReason,
    RoundRecord,
    Side,
    TeamModel,
    build_live_match,
    classify_buy,
    compute_momentum,
    compute_round_importance,
)
from tests.conftest import make_player, make_state


def test_build_live_match_headline_fields():
    state = GameState.model_validate(
        make_state(
            [
                make_player("1", "a", "CT", health=100, kills=5, equip_value=4000),
                make_player("2", "b", "CT", health=0, kills=2, equip_value=4000),
                make_player("3", "c", "T", health=50, kills=3, equip_value=800),
            ],
            round_no=8,
            ct_score=5,
            t_score=3,
            bomb="planted",
        )
    )
    match = build_live_match(state)
    assert match.map_name == "de_mirage"
    assert match.round_number == 8
    assert match.ct.score == 5
    assert match.t.score == 3
    assert match.bomb_state == "planted"
    assert match.alive_on(Side.CT) == 1
    assert match.alive_on(Side.T) == 1
    assert match.ct.players_total == 2


def test_classify_buy_thresholds():
    assert classify_buy(0, 5) == BuyType.ECO
    assert classify_buy(5 * 1000, 5) == BuyType.ECO
    assert classify_buy(5 * 2500, 5) == BuyType.FORCE
    assert classify_buy(5 * 4500, 5) == BuyType.FULL
    assert classify_buy(1000, 0) == BuyType.UNKNOWN


def test_momentum_favours_recent_winner():
    history = tuple(RoundRecord(number=i, winner=Side.T) for i in range(3))
    m = compute_momentum(history)
    assert m.value < 0  # T has all recent rounds
    assert m.leader is Side.T


def test_momentum_neutral_without_history():
    assert compute_momentum(()) == Momentum(0.0)


def test_momentum_weights_recent_rounds_more():
    # Older CT wins, most recent T wins -> should tilt toward T.
    history = (
        RoundRecord(0, winner=Side.CT),
        RoundRecord(1, winner=Side.CT),
        RoundRecord(2, winner=Side.T),
        RoundRecord(3, winner=Side.T),
        RoundRecord(4, winner=Side.T),
    )
    assert compute_momentum(history).value < 0


def test_round_importance_spikes_on_match_point():
    ct = TeamModel(Side.CT, "A", score=12)
    t = TeamModel(Side.T, "B", score=5)
    from ai_caster.match.model import SeriesState

    imp = compute_round_importance(ct, t, SeriesState(), rounds_to_win=13)
    assert imp > 0.6  # 12 is match point out of 13


def test_is_match_point_flag():
    state = GameState.model_validate(
        make_state([make_player("1", "a", "CT")], ct_score=12, t_score=4)
    )
    match = build_live_match(state, rounds_to_win=13)
    assert match.is_match_point is True


def test_round_record_reason_enum_roundtrip():
    assert RoundEndReason("bomb_defused") is RoundEndReason.BOMB_DEFUSED
