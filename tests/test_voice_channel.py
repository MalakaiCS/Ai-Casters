"""Tests for a single voice channel (queue, worker, interruption, latency)."""

from __future__ import annotations

import threading
import time

from ai_caster.voice.audio import AudioClip, ChannelDSP
from ai_caster.voice.channel import VoiceChannel
from ai_caster.voice.sink import NullSink
from ai_caster.voice.tts.synthetic import SyntheticTTS


def _wait(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _channel(sink: NullSink, **kwargs) -> VoiceChannel:
    return VoiceChannel("test", SyntheticTTS(sample_rate=8000), ChannelDSP(), sink, **kwargs)


def test_channel_speaks_line_to_sink():
    sink = NullSink()
    channel = _channel(sink)
    channel.start()
    try:
        channel.speak("hello world")
        assert _wait(lambda: sink.clips_written == 1)
        assert channel.spoken_count == 1
        assert sink.last_clip is not None and sink.last_clip.samples.size > 0
    finally:
        channel.stop()


def test_disabled_channel_stays_silent():
    sink = NullSink()
    channel = _channel(sink, enabled=False)
    channel.start()
    try:
        channel.speak("nothing")
        time.sleep(0.1)
        assert sink.clips_written == 0
    finally:
        channel.stop()


def test_set_enabled_toggles_speech():
    sink = NullSink()
    channel = _channel(sink, enabled=False)
    channel.start()
    try:
        channel.set_enabled(True)
        channel.speak("now audible")
        assert _wait(lambda: sink.clips_written == 1)
    finally:
        channel.stop()


def test_interrupt_drops_pending_queue():
    # A slow sink lets us queue several lines, then interrupt to drop them.
    class _SlowSink(NullSink):
        def write(self, clip: AudioClip) -> None:  # type: ignore[override]
            time.sleep(0.05)
            super().write(clip)

    sink = _SlowSink()
    channel = _channel(sink)
    channel.start()
    try:
        for i in range(5):
            channel.speak(f"line {i}")
        # Interrupt with a fresh line; the queued backlog is discarded.
        channel.speak("urgent", interrupt=True)
        assert _wait(lambda: not channel.is_running or channel.pending() == 0)
        # Far fewer than 6 lines reach the sink because the backlog was dropped.
        time.sleep(0.2)
        assert sink.clips_written < 6
    finally:
        channel.stop()


def test_latency_delays_output():
    sink = NullSink()
    channel = _channel(sink, latency_ms=150)
    channel.start()
    try:
        start = time.monotonic()
        channel.speak("delayed")
        assert _wait(lambda: sink.clips_written == 1, timeout=3.0)
        assert time.monotonic() - start >= 0.15
    finally:
        channel.stop()


def test_monitor_receives_processed_audio():
    class _Monitor:
        def __init__(self) -> None:
            self.count = 0
            self._lock = threading.Lock()

        def submit(self, name: str, clip: AudioClip) -> None:
            with self._lock:
                self.count += 1

    sink = NullSink()
    monitor = _Monitor()
    channel = _channel(sink, monitor=monitor)
    channel.start()
    try:
        channel.speak("mixed")
        assert _wait(lambda: monitor.count == 1)
    finally:
        channel.stop()
