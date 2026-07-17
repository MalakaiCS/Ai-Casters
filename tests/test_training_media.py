"""Tests for the compliant media-training path (Module 18).

These lock in the ethical boundary: authorized recordings are transcribed to
anonymized text + timing; unauthorized ones are refused *before* any work; and
third-party platform links are refused outright (no scraping).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_caster.training import (
    MediaSourceError,
    TrainingPipeline,
    reject_platform_url,
    transcribe_media,
)
from ai_caster.training.guardrails import AuthorizationError
from ai_caster.training.models import Authorization, TranscriptSegment


class FakeTranscriber:
    """A deterministic stand-in for Whisper — no model, no network."""

    name = "fake"

    def __init__(self, segments: list[TranscriptSegment]) -> None:
        self._segments = segments
        self.calls: list[Path] = []

    def transcribe(self, media_path: Path, *, language: str = "en") -> list[TranscriptSegment]:
        self.calls.append(Path(media_path))
        return list(self._segments)


AUTHORIZED = Authorization(authorized=True, consent_reference="OWN-2026-001", rights_holder="Me")
UNAUTHORIZED = Authorization(authorized=False)


def _media_file(tmp_path: Path, name: str = "clip.wav") -> Path:
    path = tmp_path / name
    path.write_bytes(b"not really audio, but a real file on disk")
    return path


# --- reject_platform_url --------------------------------------------------- #
@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "https://www.twitch.tv/somechannel",
        "https://clips.twitch.tv/xyz",
        "https://www.tiktok.com/@x/video/1",
        "http://vimeo.com/12345",
    ],
)
def test_reject_platform_url_refuses_streaming_sites(url):
    with pytest.raises(MediaSourceError):
        reject_platform_url(url)


def test_reject_platform_url_allows_your_own_host():
    # A direct link to your own upload is fine.
    reject_platform_url("https://cdn.my-team.example/casts/final.wav")


# --- transcribe_media ------------------------------------------------------ #
def test_authorized_media_is_transcribed_and_anonymized(tmp_path):
    media = _media_file(tmp_path)
    transcriber = FakeTranscriber(
        [
            TranscriptSegment(role="Jerry the Caster", text="What a play here", start=0.0, end=1.5),
            TranscriptSegment(role="analyst", text="Great positioning", start=1.5, end=3.0),
            TranscriptSegment(role="caster", text="   ", start=3.0, end=3.2),  # blank -> dropped
        ]
    )

    source = transcribe_media(media, transcriber, AUTHORIZED, source_id="myclip")

    assert transcriber.calls == [media]
    # Blank segment dropped; roles collapsed to generic labels (never the name).
    assert [s.role for s in source.segments] == ["commentator", "analyst"]
    assert all("Jerry" not in s.role for s in source.segments)
    assert source.source_id == "myclip"
    assert source.authorization is AUTHORIZED


def test_unauthorized_media_raises_before_transcription(tmp_path):
    media = _media_file(tmp_path)
    transcriber = FakeTranscriber([TranscriptSegment("commentator", "hi", 0.0, 1.0)])

    with pytest.raises(AuthorizationError):
        transcribe_media(media, transcriber, UNAUTHORIZED)

    # Refused before any work: the transcriber was never invoked.
    assert transcriber.calls == []


def test_platform_url_is_refused(tmp_path):
    transcriber = FakeTranscriber([])
    with pytest.raises(MediaSourceError):
        transcribe_media("https://www.youtube.com/watch?v=abc", transcriber, AUTHORIZED)
    assert transcriber.calls == []


def test_missing_media_file_raises(tmp_path):
    transcriber = FakeTranscriber([])
    with pytest.raises(MediaSourceError):
        transcribe_media(tmp_path / "nope.wav", transcriber, AUTHORIZED)


# --- pipeline.add_media ---------------------------------------------------- #
def test_pipeline_add_media_appends_source(tmp_path):
    media = _media_file(tmp_path)
    transcriber = FakeTranscriber(
        [
            TranscriptSegment("commentator", "clutch incoming right now", 0.0, 2.0),
            TranscriptSegment("commentator", "he takes the round", 2.5, 4.0),
        ]
    )
    pipeline = TrainingPipeline()

    added = pipeline.add_media(media, authorization=AUTHORIZED, transcriber=transcriber)

    assert added in pipeline.sources
    assert len(pipeline.sources) == 1
    profile = pipeline.run()
    assert profile.num_sources == 1
    assert profile.total_segments == 2
