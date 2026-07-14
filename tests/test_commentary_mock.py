"""Tests for the deterministic mock commentary provider."""

from __future__ import annotations

from ai_caster.commentary.providers.base import LLMRequest
from ai_caster.commentary.providers.mock import MockProvider


def _req(topic: str, **context) -> LLMRequest:
    return LLMRequest(
        system="s", user="u", topic=topic, speaker="play_by_play", excitement=0.7, context=context
    )


def test_kill_uses_only_provided_names():
    text = MockProvider().generate(_req("Kill", round=1, killer="Alice", victim="Bob"))
    assert "Alice" in text
    assert "Bob" in text


def test_kill_without_victim_is_generic():
    text = MockProvider().generate(_req("Kill", round=1, killer="Alice"))
    assert "Alice" in text
    assert text  # non-empty


def test_entry_and_headshot_flags_reflected():
    text = MockProvider().generate(
        _req("Kill", round=1, killer="A", victim="B", entry=True, headshot=True)
    )
    assert "Opening pick" in text
    assert "head" in text.lower()


def test_clutch_won_mentions_player_and_opponents():
    text = MockProvider().generate(_req("ClutchWon", round=5, player="hero", opponents=3))
    assert "hero" in text
    assert "3" in text


def test_bomb_and_round_topics():
    mock = MockProvider()
    assert "bomb" in mock.generate(_req("BombPlanted")).lower()
    assert "defused" in mock.generate(_req("BombDefused")).lower()
    ended = mock.generate(_req("RoundEnded", round=3, winner="CT", reason="bomb_defused"))
    assert "CT" in ended


def test_match_started_uses_map():
    text = MockProvider().generate(_req("MatchStarted", map="de_mirage"))
    assert "de_mirage" in text


def test_unknown_topic_is_safe_generic():
    text = MockProvider().generate(_req("SomethingNew"))
    assert text  # never empty, never raises


def test_deterministic_for_same_input():
    mock = MockProvider()
    a = mock.generate(_req("Kill", round=2, killer="A", victim="B"))
    b = mock.generate(_req("Kill", round=2, killer="A", victim="B"))
    assert a == b
