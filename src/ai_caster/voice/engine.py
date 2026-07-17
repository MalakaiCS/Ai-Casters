"""The Voice Engine — Module 13.

Owns the two independent channels and the monitor mix, subscribes to generated
commentary lines, and routes each line to its channel (honouring interruption).
Channels and TTS/sinks are injectable so the whole engine is tested offline with
the synthetic TTS and null sinks.
"""

from __future__ import annotations

from collections.abc import Callable

from ai_caster.commentary.lines import CommentaryLineGenerated
from ai_caster.config.models import VoiceChannelSettings, VoiceSettings
from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger
from ai_caster.voice.audio import ChannelDSP
from ai_caster.voice.channel import VoiceChannel
from ai_caster.voice.factory import create_output_sink, create_tts
from ai_caster.voice.monitor import MonitorMixer
from ai_caster.voice.sink import AudioSink
from ai_caster.voice.tts.base import TTSEngine

_log = get_logger("voice.engine")

SinkFactory = Callable[[str, int, str], AudioSink]

PLAY_BY_PLAY = "play_by_play"
ANALYST = "analyst"


def _dsp_from(settings: VoiceChannelSettings) -> ChannelDSP:
    return ChannelDSP(
        volume=settings.volume,
        muted=settings.muted,
        compressor_enabled=settings.compressor_enabled,
        compressor_threshold=settings.compressor_threshold,
        compressor_ratio=settings.compressor_ratio,
        eq_low=settings.eq_low,
        eq_mid=settings.eq_mid,
        eq_high=settings.eq_high,
        limiter_ceiling=settings.limiter_ceiling,
    )


class VoiceEngine:
    """Two independent voices + monitor mix, driven by commentary lines."""

    def __init__(
        self,
        event_bus: EventBus,
        settings: VoiceSettings,
        *,
        tts: TTSEngine | None = None,
        sink_factory: SinkFactory | None = None,
    ) -> None:
        self._bus = event_bus
        tts = tts or create_tts(settings)
        make_sink = sink_factory or create_output_sink

        monitor_sink = make_sink(settings.monitor_device, settings.sample_rate, "monitor")
        self.monitor = MonitorMixer(monitor_sink, settings.monitor_volume)

        self.play_by_play = VoiceChannel(
            PLAY_BY_PLAY,
            tts,
            _dsp_from(settings.play_by_play),
            make_sink(settings.play_by_play.output_device, settings.sample_rate, PLAY_BY_PLAY),
            voice_id=settings.play_by_play.voice_id,
            latency_ms=settings.play_by_play.latency_ms,
            monitor=self.monitor,
            enabled=settings.play_by_play.enabled,
        )
        self.analyst = VoiceChannel(
            ANALYST,
            tts,
            _dsp_from(settings.analyst),
            make_sink(settings.analyst.output_device, settings.sample_rate, ANALYST),
            voice_id=settings.analyst.voice_id,
            latency_ms=settings.analyst.latency_ms,
            monitor=self.monitor,
            enabled=settings.analyst.enabled,
        )

        self._unsubscribe = event_bus.subscribe(CommentaryLineGenerated, self._on_line)

    # ------------------------------------------------------------------ #
    def channel(self, speaker: str) -> VoiceChannel:
        return self.analyst if speaker == ANALYST else self.play_by_play

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute both voices at once (the 'mute all' control)."""
        self.play_by_play.set_muted(muted)
        self.analyst.set_muted(muted)

    def _on_line(self, event: CommentaryLineGenerated) -> None:
        line = event.line
        if line is None or not line.text:
            return
        self.channel(line.speaker).speak(line.text, interrupt=line.interrupt)

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        self.monitor.open()
        self.play_by_play.start()
        self.analyst.start()
        _log.info("Voice engine started (2 channels + monitor mix)")

    def stop(self) -> None:
        self.play_by_play.stop()
        self.analyst.stop()
        self.monitor.close()

    def dispose(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self.stop()
