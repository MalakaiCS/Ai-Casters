"""Build TTS engines and output sinks from settings.

Offline/synthetic by default; real backends (system TTS, sound devices) are used
only when selected/available, and unavailability degrades gracefully so the
engine always runs.
"""

from __future__ import annotations

import importlib.util

from ai_caster.config.models import VoiceSettings
from ai_caster.core.logging import get_logger
from ai_caster.voice.sink import AudioSink, NullSink, SoundDeviceSink
from ai_caster.voice.tts.base import TTSEngine
from ai_caster.voice.tts.synthetic import SyntheticTTS

_log = get_logger("voice.factory")


def _available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def create_tts(settings: VoiceSettings) -> TTSEngine:
    """Choose a TTS engine (synthetic by default; system if selected/available)."""
    if settings.tts_engine == "system":
        if _available("pyttsx3"):
            from ai_caster.voice.tts.system import SystemTTS

            return SystemTTS(sample_rate=settings.sample_rate)
        _log.warning("pyttsx3 not installed; using synthetic TTS.")
    return SyntheticTTS(sample_rate=settings.sample_rate)


def create_output_sink(device: str, sample_rate: int, name: str) -> AudioSink:
    """A real device sink when a device is named and sounddevice is present, else
    the offline null sink."""
    if device and _available("sounddevice"):
        return SoundDeviceSink(device=device, sample_rate=sample_rate, name=name)
    return NullSink(name=name)
