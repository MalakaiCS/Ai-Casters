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
from ai_caster.voice.tts.synthetic import SyntheticTTS

_log = get_logger("voice.tts.elevenlabs")

# HTTP statuses that mean "this key/account can't synthesize right now" — out of
# credits (402), unauthorized/bad key (401), forbidden (403). Retrying every line
# just adds latency and log spam, so once we see one we permanently fall back to
# the offline engine for the rest of the session (the show keeps talking).
_PERMANENT_STATUSES = frozenset({401, 402, 403})


class ElevenLabsTTS:
    """Text-to-speech via the ElevenLabs API.

    If the API can't be reached (out of credits, bad key, network trouble) the
    engine degrades to the offline :class:`SyntheticTTS` instead of raising, so
    the casters never go fully silent — the same graceful-fallback contract the
    rest of the app uses. Quota/auth failures switch to the fallback for the rest
    of the session; a one-off network blip only affects the line that failed.
    """

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
        # Offline safety net so a failed cloud request still produces audio.
        self._fallback = SyntheticTTS(sample_rate=self._sample_rate)
        self._degraded = False
        self._warned = False

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
        # Already gave up on the cloud this session — stay on the offline engine.
        if self._degraded:
            return self._fallback.synthesize(text, voice_id)
        try:
            data = self._post_audio(self._endpoint(voice_id), self._headers(), self._body(text))
        except _TTSRequestError as exc:
            self._handle_failure(exc)
            return self._fallback.synthesize(text, voice_id)
        return self._pcm_to_clip(data)

    def _handle_failure(self, exc: _TTSRequestError) -> None:
        """Log the cloud failure once and, for auth/quota errors, degrade for good."""
        permanent = exc.status in _PERMANENT_STATUSES
        if permanent:
            self._degraded = True
        if not self._warned:
            self._warned = True
            reason = _REASONS.get(exc.status, "the request failed")
            tail = (
                "Switching to the built-in offline voice for the rest of the session; "
                "restore ElevenLabs by adding credits or fixing the API key, then restart."
                if permanent
                else "Falling back to the offline voice for this line and retrying next time."
            )
            _log.warning("ElevenLabs TTS unavailable (%s). %s", reason, tail)

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
        except urllib.error.HTTPError as exc:  # pragma: no cover - network I/O
            raise _TTSRequestError(str(exc), status=exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:  # pragma: no cover
            raise _TTSRequestError(str(exc), status=None) from exc


class _TTSRequestError(RuntimeError):
    """Raised inside the engine when a cloud request fails; carries the HTTP status."""

    def __init__(self, message: str, *, status: int | None) -> None:
        super().__init__(f"ElevenLabs TTS request failed: {message}")
        self.status = status


_REASONS = {
    401: "the API key was rejected (401 Unauthorized)",
    402: "the account is out of credits (402 Payment Required)",
    403: "access is forbidden for this key (403)",
    429: "the API is rate-limiting requests (429)",
}
