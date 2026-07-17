"""Modules 13 & 14 — Voice Engine and Audio Routing.

Two completely independent voice channels (play-by-play, analyst), each with its
own queue, interruption logic, volume, mute, latency and DSP chain (compressor,
EQ, limiter), plus a combined monitor mix. TTS synthesis and audio-device output
sit behind interfaces with offline/synthetic defaults, so the whole engine runs
and is tested headlessly; real backends (system TTS, sound devices) load behind
the ``[voice]`` extra.
"""

from ai_caster.voice.audio import AudioClip
from ai_caster.voice.channel import VoiceChannel
from ai_caster.voice.engine import VoiceEngine

__all__ = ["AudioClip", "VoiceChannel", "VoiceEngine"]
