"""Tests for the commentary generator (role routing, fallback, worker)."""

from __future__ import annotations

import time

from ai_caster.commentary.generator import CommentaryGenerator
from ai_caster.commentary.lines import CommentaryLineGenerated
from ai_caster.commentary.providers.base import LLMRequest
from ai_caster.commentary.providers.mock import MockProvider
from ai_caster.core.events import EventBus
from ai_caster.director.directives import (
    CommentaryDirective,
    CommentaryDirectiveIssued,
    DirectiveKind,
    DirectivePriority,
    Speaker,
)


def _directive(
    speaker=Speaker.PLAY_BY_PLAY, kind=DirectiveKind.CALL, **context
) -> CommentaryDirective:
    return CommentaryDirective(
        speaker=speaker,
        kind=kind,
        priority=DirectivePriority.HIGH,
        excitement=0.8,
        topic="Kill",
        context={"round": 1, **context},
    )


class _BoomProvider:
    name = "boom"

    def generate(self, request: LLMRequest) -> str:
        raise RuntimeError("provider down")


def test_generate_produces_line_from_directive():
    bus = EventBus()
    gen = CommentaryGenerator(bus, MockProvider(), Speaker.PLAY_BY_PLAY)
    line = gen.generate(_directive(killer="Alice", victim="Bob"))
    assert line.speaker == "play_by_play"
    assert "Alice" in line.text
    assert line.provider == "mock"
    gen.dispose()


def test_provider_failure_falls_back_to_mock():
    bus = EventBus()
    gen = CommentaryGenerator(bus, _BoomProvider(), Speaker.PLAY_BY_PLAY)
    line = gen.generate(_directive(killer="Alice", victim="Bob"))
    assert line.text  # produced by the fallback
    assert line.provider == "mock"
    gen.dispose()


def test_worker_publishes_line_for_matching_role():
    bus = EventBus()
    published: list[CommentaryLineGenerated] = []
    bus.subscribe(CommentaryLineGenerated, published.append)
    gen = CommentaryGenerator(bus, MockProvider(), Speaker.PLAY_BY_PLAY)
    gen.start()
    try:
        bus.publish(CommentaryDirectiveIssued(directive=_directive(killer="Zoe", victim="Max")))
        deadline = time.monotonic() + 2.0
        while not published and time.monotonic() < deadline:
            time.sleep(0.01)
        assert published, "no commentary line published"
        assert "Zoe" in published[0].line.text
    finally:
        gen.dispose()


def test_generator_ignores_other_role_and_silence():
    bus = EventBus()
    published: list = []
    bus.subscribe(CommentaryLineGenerated, published.append)
    gen = CommentaryGenerator(bus, MockProvider(), Speaker.ANALYST)  # analyst
    gen.start()
    try:
        # A play-by-play directive must be ignored by the analyst generator.
        bus.publish(CommentaryDirectiveIssued(directive=_directive(speaker=Speaker.PLAY_BY_PLAY)))
        # A silence directive is ignored by everyone.
        bus.publish(
            CommentaryDirectiveIssued(
                directive=CommentaryDirective(
                    speaker=Speaker.NONE,
                    kind=DirectiveKind.SILENCE,
                    priority=DirectivePriority.AMBIENT,
                    excitement=0.0,
                    topic="Kill",
                )
            )
        )
        time.sleep(0.15)
        assert published == []
    finally:
        gen.dispose()


def test_disabled_generator_produces_nothing():
    bus = EventBus()
    published: list = []
    bus.subscribe(CommentaryLineGenerated, published.append)
    gen = CommentaryGenerator(bus, MockProvider(), Speaker.PLAY_BY_PLAY, enabled=False)
    gen.start()
    try:
        bus.publish(CommentaryDirectiveIssued(directive=_directive(killer="A")))
        time.sleep(0.15)
        assert published == []
    finally:
        gen.dispose()


class _FixedProvider:
    """Always returns the same text — to exercise the duplicate guard."""

    name = "fixed"

    def __init__(self, text: str) -> None:
        self._text = text

    def generate(self, request: LLMRequest) -> str:
        return self._text


def test_worker_drops_a_consecutive_duplicate_line():
    bus = EventBus()
    lines: list = []
    bus.subscribe(CommentaryLineGenerated, lines.append)
    gen = CommentaryGenerator(bus, _FixedProvider("Insane clutch!"), Speaker.PLAY_BY_PLAY)
    gen.start()
    try:
        # Two identical directives back to back must only speak once.
        gen._on_directive(CommentaryDirectiveIssued(directive=_directive()))
        gen._on_directive(CommentaryDirectiveIssued(directive=_directive()))
        deadline = time.time() + 2.0
        while len(gen.recent_lines()) < 1 and time.time() < deadline:
            time.sleep(0.01)
        time.sleep(0.1)  # give the second one a chance to (not) publish
    finally:
        gen.stop()
    texts = [event.line.text for event in lines]
    assert texts.count("Insane clutch!") == 1  # the duplicate was suppressed
