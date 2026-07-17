"""Tests for cross-caster banter: the shared conversation memory and prompt."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_caster.commentary.conversation import ConversationMemory
from ai_caster.commentary.lines import CommentaryLine, CommentaryLineGenerated
from ai_caster.commentary.prompts import user_prompt
from ai_caster.commentary.providers.base import LLMRequest
from ai_caster.commentary.providers.mock import MockProvider
from ai_caster.core.events import EventBus
from ai_caster.director.directives import (
    CommentaryDirective,
    DirectiveKind,
    DirectivePriority,
    Speaker,
)


def _line(speaker: str, text: str) -> CommentaryLine:
    return CommentaryLine(
        speaker=speaker,
        text=text,
        topic="Kill",
        excitement=0.8,
        provider="mock",
        directive_kind="call",
    )


# --- shared conversation memory -------------------------------------------- #
def test_memory_records_lines_from_the_bus():
    bus = EventBus()
    memory = ConversationMemory(bus)
    bus.publish(CommentaryLineGenerated(line=_line("play_by_play", "Big frag!")))
    bus.publish(CommentaryLineGenerated(line=_line("analyst", "Read it perfectly.")))
    turns = memory.recent()
    assert [t.speaker for t in turns] == ["play_by_play", "analyst"]
    assert turns[-1].text == "Read it perfectly."


def test_last_from_other_ignores_own_lines():
    bus = EventBus()
    memory = ConversationMemory(bus)
    memory.record("play_by_play", "Opening pick!", datetime.now(UTC))
    memory.record("analyst", "That sets the tone.", datetime.now(UTC))
    other = memory.last_from_other("play_by_play")
    assert other is not None and other.speaker == "analyst"
    assert memory.last_from_other("analyst").speaker == "play_by_play"


def test_dispose_unsubscribes():
    bus = EventBus()
    memory = ConversationMemory(bus)
    memory.dispose()
    bus.publish(CommentaryLineGenerated(line=_line("analyst", "late line")))
    assert memory.recent() == ()


# --- prompt rendering ------------------------------------------------------ #
def _directive() -> CommentaryDirective:
    return CommentaryDirective(
        speaker=Speaker.ANALYST,
        kind=DirectiveKind.HANDOFF,
        priority=DirectivePriority.LOW,
        excitement=0.5,
        topic="reaction",
    )


def test_user_prompt_includes_exchange_and_reaction_nudge():
    conversation = (("play_by_play", "hero wins the clutch!"),)
    prompt = user_prompt(_directive(), (), conversation, speaker="analyst")
    assert "Recent desk exchange" in prompt
    assert "hero wins the clutch!" in prompt
    assert "co-caster just spoke" in prompt
    # The co-caster's line is labelled from the analyst's point of view.
    assert "[co-caster]" in prompt


def test_user_prompt_no_reaction_nudge_when_you_spoke_last():
    conversation = (("analyst", "my own last line"),)
    prompt = user_prompt(_directive(), (), conversation, speaker="analyst")
    assert "[you]" in prompt
    assert "co-caster just spoke" not in prompt


# --- offline banter rendering ---------------------------------------------- #
def test_mock_prefixes_connective_when_reacting():
    req = LLMRequest(
        system="s",
        user="u",
        topic="reaction",
        speaker="analyst",
        excitement=0.6,
        conversation=(("play_by_play", "clutch of the tournament!"),),
    )
    text = MockProvider().generate(req)
    # A connective lead-in makes it read as an answer to the play-by-play.
    assert any(text.startswith(c) for c in ("Right —", "Exactly —", "And on that,", "Building on"))


def test_mock_no_connective_without_co_caster_turn():
    req = LLMRequest(
        system="s",
        user="u",
        topic="reaction",
        speaker="analyst",
        excitement=0.6,
        conversation=(("analyst", "my own prior line"),),
    )
    text = MockProvider().generate(req)
    assert not text.startswith(("Right —", "Exactly —", "And on that,", "Building on"))
