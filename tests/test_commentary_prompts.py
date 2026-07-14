"""Tests for the commentary prompt builders."""

from __future__ import annotations

from ai_caster.commentary.prompts import system_prompt, user_prompt
from ai_caster.director.directives import (
    CommentaryDirective,
    DirectiveKind,
    DirectivePriority,
    Speaker,
)


def test_system_prompt_encodes_hard_rules():
    text = system_prompt(Speaker.PLAY_BY_PLAY.value, "en")
    lowered = text.lower()
    assert "only the facts" in lowered
    assert "never invent" in lowered
    assert "do not imitate" in lowered
    assert "english" in lowered


def test_system_prompt_role_and_language():
    pbp = system_prompt(Speaker.PLAY_BY_PLAY.value, "es")
    analyst = system_prompt(Speaker.ANALYST.value, "en")
    assert "play-by-play" in pbp.lower()
    assert "Spanish" in pbp
    assert "analyst" in analyst.lower()


def test_user_prompt_lists_only_supplied_facts():
    directive = CommentaryDirective(
        speaker=Speaker.PLAY_BY_PLAY,
        kind=DirectiveKind.CALL,
        priority=DirectivePriority.HIGH,
        excitement=0.8,
        topic="Kill",
        context={"killer": "Alice", "victim": "Bob"},
    )
    text = user_prompt(directive)
    assert "Kill" in text
    assert "killer=Alice" in text
    assert "victim=Bob" in text
    assert "0.80" in text
