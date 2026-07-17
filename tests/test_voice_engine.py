"""Tests for the Voice Engine (line routing, monitor mix, offline defaults)."""

from __future__ import annotations

import time

from ai_caster.commentary.lines import CommentaryLine, CommentaryLineGenerated
from ai_caster.config.models import VoiceSettings
from ai_caster.core.events import EventBus
from ai_caster.voice.engine import ANALYST, PLAY_BY_PLAY, VoiceEngine
from ai_caster.voice.sink import NullSink


class _RecordingSinkFactory:
    """Hands out (and remembers) a NullSink per channel name."""

    def __init__(self) -> None:
        self.sinks: dict[str, NullSink] = {}

    def __call__(self, device: str, sample_rate: int, name: str) -> NullSink:
        sink = NullSink(name=name)
        self.sinks[name] = sink
        return sink


def _line(speaker: str, text: str = "a call", interrupt: bool = False) -> CommentaryLine:
    return CommentaryLine(
        speaker=speaker,
        text=text,
        topic="Kill",
        excitement=0.8,
        provider="mock",
        directive_kind="call",
        interrupt=interrupt,
    )


def _wait(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _engine(bus: EventBus, factory: _RecordingSinkFactory) -> VoiceEngine:
    settings = VoiceSettings(sample_rate=8000)
    return VoiceEngine(bus, settings, sink_factory=factory)


def test_line_routes_to_matching_channel():
    bus = EventBus()
    factory = _RecordingSinkFactory()
    engine = _engine(bus, factory)
    engine.start()
    try:
        bus.publish(CommentaryLineGenerated(line=_line(PLAY_BY_PLAY, "the kill")))
        assert _wait(lambda: factory.sinks[PLAY_BY_PLAY].clips_written == 1)
        # Analyst channel stayed silent.
        time.sleep(0.05)
        assert factory.sinks[ANALYST].clips_written == 0
    finally:
        engine.dispose()


def test_analyst_line_routes_to_analyst():
    bus = EventBus()
    factory = _RecordingSinkFactory()
    engine = _engine(bus, factory)
    engine.start()
    try:
        bus.publish(CommentaryLineGenerated(line=_line(ANALYST, "context here")))
        assert _wait(lambda: factory.sinks[ANALYST].clips_written == 1)
        assert factory.sinks[PLAY_BY_PLAY].clips_written == 0
    finally:
        engine.dispose()


def test_monitor_mix_receives_both_channels():
    bus = EventBus()
    factory = _RecordingSinkFactory()
    engine = _engine(bus, factory)
    engine.start()
    try:
        bus.publish(CommentaryLineGenerated(line=_line(PLAY_BY_PLAY)))
        bus.publish(CommentaryLineGenerated(line=_line(ANALYST)))
        monitor = factory.sinks["monitor"]
        assert _wait(lambda: monitor.clips_written >= 2)
    finally:
        engine.dispose()


def test_empty_and_none_lines_are_ignored():
    bus = EventBus()
    factory = _RecordingSinkFactory()
    engine = _engine(bus, factory)
    engine.start()
    try:
        bus.publish(CommentaryLineGenerated(line=None))
        bus.publish(CommentaryLineGenerated(line=_line(PLAY_BY_PLAY, text="")))
        time.sleep(0.1)
        assert factory.sinks[PLAY_BY_PLAY].clips_written == 0
    finally:
        engine.dispose()


def test_dispose_unsubscribes_from_bus():
    bus = EventBus()
    factory = _RecordingSinkFactory()
    engine = _engine(bus, factory)
    engine.start()
    engine.dispose()
    # After dispose, further lines are not consumed.
    bus.publish(CommentaryLineGenerated(line=_line(PLAY_BY_PLAY)))
    time.sleep(0.1)
    assert factory.sinks[PLAY_BY_PLAY].clips_written == 0


def test_channel_lookup_by_speaker():
    bus = EventBus()
    engine = _engine(bus, _RecordingSinkFactory())
    try:
        assert engine.channel(ANALYST) is engine.analyst
        assert engine.channel(PLAY_BY_PLAY) is engine.play_by_play
        # Unknown speaker defaults to play-by-play.
        assert engine.channel("unknown") is engine.play_by_play
    finally:
        engine.dispose()
