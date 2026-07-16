"""Tests for the authorized YouTube-captions training path."""

from __future__ import annotations

import pytest

import ai_caster.training.youtube as yt
from ai_caster.training.guardrails import AuthorizationError
from ai_caster.training.models import Authorization, TranscriptSegment
from ai_caster.training.pipeline import TrainingPipeline
from ai_caster.training.youtube import (
    YouTubeTranscriptError,
    _to_segments,
    extract_video_id,
)

AUTHORIZED = Authorization(authorized=True, consent_reference="OWN-YT-2026", rights_holder="Me")
UNAUTHORIZED = Authorization(authorized=False)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_extract_video_id(url, expected):
    assert extract_video_id(url) == expected


def test_extract_video_id_rejects_non_youtube():
    with pytest.raises(YouTubeTranscriptError):
        extract_video_id("https://example.com/watch?x=1")


def test_to_segments_maps_and_filters():
    raw = [
        {"text": "clutch play here", "start": 0.0, "duration": 2.0},
        {"text": "[Music]", "start": 2.0, "duration": 1.0},  # dropped
        {"text": "  ", "start": 3.0, "duration": 1.0},  # dropped
        {"text": "he takes the round", "start": 4.0, "duration": 1.5},
    ]
    segments = _to_segments(raw)
    assert [s.text for s in segments] == ["clutch play here", "he takes the round"]
    assert segments[0].role == "commentator"
    assert segments[1].end == pytest.approx(5.5)


def test_pipeline_add_youtube_authorized(monkeypatch):
    def fake_fetch(url, *, languages=("en",)):
        return [
            TranscriptSegment("caster", "great positioning", 0.0, 2.0),
            TranscriptSegment("analyst", "textbook execute", 2.0, 4.0),
        ]

    monkeypatch.setattr(yt, "fetch_youtube_transcript", fake_fetch)
    # pipeline.add_youtube imports fetch_youtube_transcript from the module, so patch there too.
    import ai_caster.training.pipeline as pipe_mod  # noqa: F401

    pipeline = TrainingPipeline()
    source = pipeline.add_youtube(
        "https://youtu.be/dQw4w9WgXcQ", authorization=AUTHORIZED
    )
    assert source in pipeline.sources
    assert source.source_id == "dQw4w9WgXcQ"
    # Roles are anonymized to generic labels.
    assert [s.role for s in source.segments] == ["commentator", "analyst"]


def test_pipeline_add_youtube_unauthorized_raises(monkeypatch):
    calls = {"fetched": False}

    def fake_fetch(url, *, languages=("en",)):
        calls["fetched"] = True
        return []

    monkeypatch.setattr(yt, "fetch_youtube_transcript", fake_fetch)
    pipeline = TrainingPipeline()
    with pytest.raises(AuthorizationError):
        pipeline.add_youtube("https://youtu.be/dQw4w9WgXcQ", authorization=UNAUTHORIZED)
    # Refused before any network work.
    assert calls["fetched"] is False
