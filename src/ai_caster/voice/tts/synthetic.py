"""Offline synthetic TTS — the default engine.

Produces a short, deterministic tone whose length scales with the text, with a
smooth amplitude envelope. It generates no words, but it exercises the entire
voice path (queue, DSP, interruption, routing, monitor mix) with real audio
samples and zero dependencies — which is what makes the engine testable and lets
the app run on any machine. A distinct base pitch per voice id keeps the two
channels audibly different.
"""

from __future__ import annotations

import numpy as np

from ai_caster.voice.audio import AudioClip

_SECONDS_PER_CHAR = 0.045
_MIN_SECONDS = 0.3
_MAX_SECONDS = 12.0


class SyntheticTTS:
    """Deterministic tone-based TTS for development and CI."""

    name = "synthetic"

    def __init__(self, sample_rate: int = 24000, base_hz: float = 150.0) -> None:
        self._sample_rate = sample_rate
        self._base_hz = base_hz

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def synthesize(self, text: str, voice_id: str = "") -> AudioClip:
        duration = min(_MAX_SECONDS, max(_MIN_SECONDS, len(text) * _SECONDS_PER_CHAR))
        n = int(duration * self._sample_rate)
        if n <= 0:
            return AudioClip(np.zeros(0, dtype=np.float32), self._sample_rate)

        t = np.arange(n, dtype=np.float32) / self._sample_rate
        # Voice id nudges the pitch so channels are distinguishable.
        pitch = self._base_hz + (abs(hash(voice_id)) % 60)
        tone = 0.4 * np.sin(2 * np.pi * pitch * t)
        # Gentle attack/release envelope.
        env = np.ones(n, dtype=np.float32)
        ramp = min(n // 2, int(0.02 * self._sample_rate))
        if ramp > 0:
            env[:ramp] = np.linspace(0.0, 1.0, ramp)
            env[-ramp:] = np.linspace(1.0, 0.0, ramp)
        return AudioClip((tone * env).astype(np.float32), self._sample_rate)
