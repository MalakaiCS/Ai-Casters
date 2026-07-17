"""System TTS via pyttsx3 (optional, ``[voice]`` extra).

Renders real speech with the OS voice (SAPI5 on Windows, NSSpeech on macOS,
espeak on Linux) to a temporary WAV, then loads it back as samples. Lazy-imports
pyttsx3 so the package only needs it when this engine is selected.
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

import numpy as np

from ai_caster.core.logging import get_logger
from ai_caster.voice.audio import AudioClip

_log = get_logger("voice.tts.system")


class SystemTTS:
    """OS text-to-speech via pyttsx3."""

    name = "system"

    def __init__(self, sample_rate: int = 24000) -> None:
        self._sample_rate = sample_rate

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def _engine(self):
        try:
            import pyttsx3  # type: ignore
        except ImportError as exc:  # pragma: no cover - only without pyttsx3
            raise RuntimeError(
                "System TTS requires pyttsx3. Install voice extras: "
                'pip install "ai-esports-caster[voice]"'
            ) from exc
        return pyttsx3.init()

    def synthesize(self, text: str, voice_id: str = "") -> AudioClip:
        engine = self._engine()
        if voice_id:
            engine.setProperty("voice", voice_id)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "line.wav"
            engine.save_to_file(text, str(path))
            engine.runAndWait()
            return self._load_wav(path)

    def _load_wav(self, path: Path) -> AudioClip:
        with wave.open(str(path), "rb") as wav:
            rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
            width = wav.getsampwidth()
            channels = wav.getnchannels()
        if width == 2:
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        elif width == 1:
            data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        else:  # pragma: no cover - uncommon sample widths
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            data = data.reshape(-1, channels).mean(axis=1)
        return AudioClip(data.astype(np.float32), rate)
