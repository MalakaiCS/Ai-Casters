"""The combined monitor mix.

Both channels forward their processed audio here; the mixer applies the monitor
volume and sends it to the monitor sink (e.g. the caster's headphones), so the
operator hears both voices together. Since the Commentary Director serialises who
speaks, the two channels rarely overlap; when they don't, the monitor is a faithful
combined feed. Sample-accurate summation of concurrent speech is a later
enhancement — the :func:`~ai_caster.voice.audio.mix` primitive already exists for it.
"""

from __future__ import annotations

from ai_caster.voice.audio import AudioClip, apply_gain
from ai_caster.voice.sink import AudioSink


class MonitorMixer:
    """Forwards both channels' audio to the monitor sink at the monitor volume."""

    def __init__(self, sink: AudioSink, volume: float = 0.8) -> None:
        self._sink = sink
        self._volume = volume

    @property
    def sink(self) -> AudioSink:
        return self._sink

    def set_volume(self, volume: float) -> None:
        self._volume = volume

    def open(self) -> None:
        self._sink.open()

    def close(self) -> None:
        self._sink.close()

    def submit(self, channel_name: str, clip: AudioClip) -> None:
        if self._volume <= 0.0 or clip.samples.size == 0:
            return
        self._sink.write(clip.with_samples(apply_gain(clip.samples, self._volume)))
