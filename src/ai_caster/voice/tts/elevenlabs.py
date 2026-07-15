"""ElevenLabs cloud TTS — production-quality voices.

Talks to the ElevenLabs text-to-speech REST API and returns raw PCM as an
:class:`AudioClip`, so it slots into the exact same voice path as the offline
engines. Uses only stdlib HTTP (no SDK dependency) — it just needs an API key.
Request building and PCM decoding are pure and unit-tested; only the network
call is platform/credential dependent.

Each voice channel's ``voice_id`` selects the ElevenLabs voice, so play-by-play
and the analyst can use different voices.
"""

from __future__ import annotations

import numpy as np

from ai_caster.core.logging import get_logger
from ai_caster.voice.audio import AudioClip

_log = get_logger("voice.tts.elevenlabs")


class ElevenLabsTTS:
    """Text-to-speech via the ElevenLabs API."""

    name = "elevenlabs"

    _API = "https://api.elevenlabs.io/v1/text-to-speech"
    # A stock ElevenLabs voice used when a channel has no voice id configured.
    DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"
    _SUPPORTED_RATES = (16000, 22050, 24000, 44100)

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "eleven_turbo_v2_5",
        sample_rate: int = 24000,
        default_voice_id: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._key = api_key
        self._model = model
        self._sample_rate = sample_rate if sample_rate in self._SUPPORTED_RATES else 24000
        self._default_voice = default_voice_id or self.DEFAULT_VOICE
        self._timeout = timeout

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    # -- pure helpers --------------------------------------------------- #
    def _endpoint(self, voice_id: str) -> str:
        vid = voice_id or self._default_voice
        return f"{self._API}/{vid}?output_format=pcm_{self._sample_rate}"

    def _headers(self) -> dict[str, str]:
        return {
            "xi-api-key": self._key,
            "Content-Type": "application/json",
            "Accept": "audio/pcm",
        }

    def _body(self, text: str) -> dict:
        return {
            "text": text,
            "model_id": self._model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }

    def _pcm_to_clip(self, data: bytes) -> AudioClip:
        # ElevenLabs pcm_* output is signed 16-bit little-endian mono.
        samples = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
        return AudioClip(samples.copy(), self._sample_rate)

    # -- engine interface ----------------------------------------------- #
    def synthesize(self, text: str, voice_id: str = "") -> AudioClip:
        if not text.strip():
            return AudioClip(np.zeros(0, dtype=np.float32), self._sample_rate)
        data = self._post_audio(self._endpoint(voice_id), self._headers(), self._body(text))
        return self._pcm_to_clip(data)

    def _post_audio(self, url: str, headers: dict[str, str], body: dict) -> bytes:
        import json
        import urllib.error
        import urllib.request

        request = urllib.request.Request(  # pragma: no cover - network I/O
            url, data=json.dumps(body).encode("utf-8"), method="POST"
        )
        for key, value in headers.items():  # pragma: no cover - network I/O
            request.add_header(key, value)
        try:  # pragma: no cover - network I/O
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:  # pragma: no cover
            raise RuntimeError(f"ElevenLabs TTS request failed: {exc}") from exc
