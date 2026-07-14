"""Text-to-speech engines behind one interface."""

from ai_caster.voice.tts.base import TTSEngine
from ai_caster.voice.tts.synthetic import SyntheticTTS

__all__ = ["TTSEngine", "SyntheticTTS"]
