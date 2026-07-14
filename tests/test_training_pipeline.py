"""Tests for the end-to-end training pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_caster.training.guardrails import AuthorizationError
from ai_caster.training.models import Authorization, TrainingSource, TranscriptSegment
from ai_caster.training.pipeline import TrainingPipeline

_AUTH = Authorization(authorized=True, consent_reference="C-1")


def _source(sid: str = "s") -> TrainingSource:
    return TrainingSource(
        sid,
        _AUTH,
        segments=[
            TranscriptSegment("play_by_play", "what a clutch play right there", 0.0, 2.0),
            TranscriptSegment("analyst", "the clutch play was clean", 2.5, 4.0),
        ],
        language="en",
    )


def test_pipeline_runs_and_builds_profile():
    pipeline = TrainingPipeline(min_term_count=2)
    pipeline.add_source(_source("a"))
    pipeline.add_source(_source("b"))
    profile = pipeline.run()
    assert profile.num_sources == 2
    assert profile.total_segments == 4
    assert profile.pacing.segments_analyzed == 4
    assert profile.vocabulary.tokens_analyzed > 0
    assert any(term == "clutch" for term, _ in profile.vocabulary.top_terms)


def test_pipeline_rejects_unauthorized_source():
    pipeline = TrainingPipeline()
    bad = TrainingSource("bad", Authorization(authorized=False))
    with pytest.raises(AuthorizationError):
        pipeline.add_source(bad)


def test_pipeline_add_directory(tmp_path: Path):
    raw = {
        "source_id": "m1",
        "authorization": {"authorized": True, "consent_reference": "C-9"},
        "segments": [{"role": "analyst", "text": "great round here", "start": 0, "end": 2}],
    }
    (tmp_path / "m1.json").write_text(json.dumps(raw), encoding="utf-8")
    pipeline = TrainingPipeline()
    assert pipeline.add_directory(tmp_path) == 1
    assert pipeline.run().num_sources == 1


def test_save_profile_roundtrips(tmp_path: Path):
    pipeline = TrainingPipeline()
    pipeline.add_source(_source())
    profile = pipeline.run()
    out = tmp_path / "profiles" / "style.json"
    pipeline.save_profile(profile, out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["kind"] == "ai_caster.style_profile"
    assert data["total_segments"] == 2
    assert "pacing" in data and "vocabulary" in data


def test_suggested_settings_are_clamped():
    pipeline = TrainingPipeline()
    pipeline.add_source(_source())
    profile = pipeline.run()
    suggested = pipeline.suggested_director_settings(profile)
    assert 200 <= suggested["min_speech_gap_ms"] <= 2000
    assert "note" in suggested


def test_summary_is_human_readable():
    pipeline = TrainingPipeline()
    pipeline.add_source(_source())
    text = pipeline.summary(pipeline.run())
    assert "Style profile" in text
    assert "Pacing:" in text and "Vocabulary:" in text
