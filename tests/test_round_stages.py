"""Tests for round stages, team-name recognition, and map-control commentary."""

from __future__ import annotations

from ai_caster.commentary.mapcontrol import area_for, areas_for
from ai_caster.commentary.providers.base import LLMRequest
from ai_caster.commentary.providers.mock import MockProvider
from ai_caster.core.events import EventBus
from ai_caster.detection.events import RoundEnded
from ai_caster.director.director import CommentaryDirector
from ai_caster.gsi.models import GameState
from ai_caster.match.events import MatchModelUpdated
from ai_caster.match.model import (
    LiveMatch,
    Side,
    TeamModel,
    build_live_match,
    round_stage_for,
)


# --- round stages ---------------------------------------------------------- #
def test_round_stage_thresholds():
    assert round_stage_for(115.0, "live") == 1  # opening (>1:30 left)
    assert round_stage_for(91.0, "live") == 1
    assert round_stage_for(90.0, "live") == 2  # 1:30 down to 0:45
    assert round_stage_for(46.0, "live") == 2
    assert round_stage_for(45.0, "live") == 3  # under 0:45
    assert round_stage_for(5.0, "live") == 3
    assert round_stage_for(None, "live") == 1  # live, clock unknown -> opening
    assert round_stage_for(80.0, "freezetime") == 0  # not a live round


def test_build_live_match_reads_round_clock_and_stage():
    payload = {
        "provider": {"name": "cs2", "appid": 730, "timestamp": 1},
        "map": {"name": "de_inferno", "phase": "live"},
        "round": {"phase": "live"},
        "phase_countdowns": {"phase": "live", "phase_ends_in": "42.5"},
        "allplayers": {},
    }
    live = build_live_match(GameState.model_validate(payload))
    assert live.round_time_left == 42.5
    assert live.round_stage == 3  # under 0:45


# --- team-name recognition (Faceit/ESEA) ----------------------------------- #
def test_team_name_prefers_real_names():
    named = LiveMatch(ct=TeamModel(Side.CT, "Vitality"), t=TeamModel(Side.T, "FaZe"))
    assert named.team_name(Side.CT) == "Vitality"
    assert named.team_name(Side.T) == "FaZe"
    assert named.has_team_names

    plain = LiveMatch(ct=TeamModel(Side.CT, "CT"), t=TeamModel(Side.T, "T"))
    assert plain.team_name(Side.CT) == "CT"
    assert not plain.has_team_names


def test_mock_uses_team_name_when_present():
    mock = MockProvider()
    named = mock.generate(
        LLMRequest(
            system="s",
            user="u",
            topic="RoundEnded",
            speaker="play_by_play",
            excitement=0.6,
            context={"winner": "CT", "winner_team": "Vitality", "reason": "elimination"},
        )
    )
    assert "Vitality" in named
    assert "CT side" not in named


def test_director_enriches_context_with_team_names():
    bus = EventBus()
    director = CommentaryDirector(bus)
    # Feed a model carrying real team names.
    match = LiveMatch(ct=TeamModel(Side.CT, "Vitality"), t=TeamModel(Side.T, "FaZe"))
    bus.publish(MatchModelUpdated(match=match))
    directives = director.handle_match_event(RoundEnded(round_number=3, winner="CT"))
    call = directives[0]
    assert call.context["ct_team"] == "Vitality"
    assert call.context["t_team"] == "FaZe"
    assert call.context["winner_team"] == "Vitality"
    director.dispose()


# --- map control ----------------------------------------------------------- #
def test_map_areas_known_and_fallback():
    assert "Banana" in areas_for("de_inferno")
    assert areas_for("de_inferno") == areas_for("inferno")  # prefix-tolerant
    assert areas_for("de_unknownmap")  # generic fallback, non-empty
    assert area_for("de_inferno", 0) == "Banana"


def test_map_control_line_mentions_the_area_and_stays_expectational():
    mock = MockProvider()
    line = mock.generate(
        LLMRequest(
            system="s",
            user="u",
            topic="map_control",
            speaker="analyst",
            excitement=0.25,
            context={
                "map": "de_inferno",
                "area": "Banana",
                "ct_team": "Vitality",
                "t_team": "FaZe",
            },
        )
    )
    assert "Banana" in line
    assert "de_inferno" in line or "Vitality" in line or "FaZe" in line
