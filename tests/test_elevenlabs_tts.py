"""Tests for the ElevenLabs TTS engine and its factory selection."""

from __future__ import annotations

import numpy as np

from ai_caster.config.models import VoiceSettings
from ai_caster.voice.factory import create_tts
from ai_caster.voice.tts.elevenlabs import ElevenLabsTTS
from ai_caster.voice.tts.synthetic import SyntheticTTS

KEY = "xi-test-key"


def _engine(**kwargs) -> ElevenLabsTTS:
    return ElevenLabsTTS(KEY, sample_rate=24000, **kwargs)


def test_endpoint_uses_voice_and_output_format():
    engine = _engine()
    url = engine._endpoint("voiceA")
    assert url.endswith("/text-to-speech/voiceA?output_format=pcm_24000")
    # Falls back to the default voice when none is given.
    assert engine.DEFAULT_VOICE in engine._endpoint("")


def test_headers_include_api_key():
    headers = _engine()._headers()
    assert headers["xi-api-key"] == KEY
    assert headers["Accept"] == "audio/pcm"


def test_body_shape():
    body = _engine(model="eleven_flash_v2_5")._body("Nice frag!")
    assert body["text"] == "Nice frag!"
    assert body["model_id"] == "eleven_flash_v2_5"
    assert "voice_settings" in body


def test_unsupported_sample_rate_falls_back_to_24k():
    assert ElevenLabsTTS(KEY, sample_rate=11025).sample_rate == 24000
    assert ElevenLabsTTS(KEY, sample_rate=44100).sample_rate == 44100


def test_pcm_to_clip_decodes_int16():
    # int16 PCM: 0, 16384 (=0.5), -16384 (=-0.5)
    pcm = np.array([0, 16384, -16384], dtype="<i2").tobytes()
    clip = _engine()._pcm_to_clip(pcm)
    assert clip.sample_rate == 24000
    assert np.allclose(clip.samples, [0.0, 0.5, -0.5], atol=1e-4)


def test_synthesize_uses_post_audio(monkeypatch):
    engine = _engine()
    pcm = np.array([1000, -1000], dtype="<i2").tobytes()
    calls = {}

    def fake_post(url, headers, body):
        calls["url"] = url
        calls["body"] = body
        return pcm

    monkeypatch.setattr(engine, "_post_audio", fake_post)
    clip = engine.synthesize("Clutch!", "voiceB")
    assert clip.samples.size == 2
    assert "voiceB" in calls["url"]
    assert calls["body"]["text"] == "Clutch!"


def test_synthesize_empty_text_is_silence():
    clip = _engine().synthesize("   ", "v")
    assert clip.samples.size == 0


# --- graceful fallback ----------------------------------------------------- #
from ai_caster.voice.tts.elevenlabs import _TTSRequestError  # noqa: E402


def test_payment_required_falls_back_to_synthetic_audio(monkeypatch):
    """402 (out of credits) must produce audio, not raise or go silent."""
    engine = _engine()

    def boom(url, headers, body):
        raise _TTSRequestError("HTTP Error 402: Payment Required", status=402)

    monkeypatch.setattr(engine, "_post_audio", boom)
    clip = engine.synthesize("Insane clutch!", "voiceB")
    # Real audio came back from the offline fallback engine.
    assert clip.samples.size > 0
    assert clip.sample_rate == engine.sample_rate


def test_permanent_failure_degrades_for_the_session(monkeypatch):
    """After a 402 the engine stops calling the cloud and stays on synthetic."""
    engine = _engine()
    calls = {"n": 0}

    def boom(url, headers, body):
        calls["n"] += 1
        raise _TTSRequestError("HTTP Error 402: Payment Required", status=402)

    monkeypatch.setattr(engine, "_post_audio", boom)
    engine.synthesize("first", "v")
    engine.synthesize("second", "v")
    engine.synthesize("third", "v")
    # Only the first line actually hit the network; the rest short-circuited.
    assert calls["n"] == 1
    assert engine._degraded is True


def test_transient_network_error_retries_next_line(monkeypatch):
    """A one-off network blip falls back but keeps trying the cloud."""
    engine = _engine()
    calls = {"n": 0}

    def flaky(url, headers, body):
        calls["n"] += 1
        raise _TTSRequestError("connection reset", status=None)

    monkeypatch.setattr(engine, "_post_audio", flaky)
    engine.synthesize("one", "v")
    engine.synthesize("two", "v")
    # Both lines attempted the network — not permanently degraded.
    assert calls["n"] == 2
    assert engine._degraded is False


# --- factory --------------------------------------------------------------- #
def test_factory_selects_elevenlabs_with_key():
    settings = VoiceSettings(tts_engine="elevenlabs", elevenlabs_api_key=KEY)
    assert isinstance(create_tts(settings), ElevenLabsTTS)


def test_factory_falls_back_without_key():
    settings = VoiceSettings(tts_engine="elevenlabs")  # no key
    assert isinstance(create_tts(settings), SyntheticTTS)
