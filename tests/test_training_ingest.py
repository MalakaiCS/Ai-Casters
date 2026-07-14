"""Tests for loading and parsing authorized transcript sources."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_caster.training.guardrails import AudioInputRejected, AuthorizationError
from ai_caster.training.ingest import load_sources, parse_source

_AUTH = {"authorized": True, "consent_reference": "CONSENT-42", "rights_holder": "League"}


def _raw(**over):
    base = {
        "source_id": "match-1",
        "language": "en",
        "authorization": dict(_AUTH),
        "segments": [
            {"role": "play-by-play", "text": "What a clutch play here", "start": 0.0, "end": 2.0},
            {"role": "colour", "text": "The positioning was perfect", "start": 2.5, "end": 4.0},
        ],
    }
    base.update(over)
    return base


def test_parse_valid_source_anonymizes_roles():
    source = parse_source(_raw())
    assert source.source_id == "match-1"
    assert [s.role for s in source.segments] == ["play_by_play", "analyst"]
    assert source.segments[0].word_count == 5


def test_parse_refuses_unauthorized():
    with pytest.raises(AuthorizationError):
        parse_source(_raw(authorization={"authorized": False, "consent_reference": ""}))


def test_parse_refuses_audio():
    with pytest.raises(AudioInputRejected):
        parse_source(_raw(audio_path="match1.wav"))


def test_parse_skips_empty_text_segments():
    raw = _raw(segments=[{"role": "analyst", "text": "   ", "start": 0, "end": 1}])
    source = parse_source(raw)
    assert source.segments == []


def _write(path: Path, raw: dict) -> None:
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_load_sources_skips_unauthorized_by_default(tmp_path: Path):
    _write(tmp_path / "ok.json", _raw(source_id="ok"))
    _write(
        tmp_path / "bad.json",
        _raw(source_id="bad", authorization={"authorized": False, "consent_reference": ""}),
    )
    _write(tmp_path / "audio.json", _raw(source_id="aud", audio="x.wav"))
    sources = load_sources(tmp_path)
    assert [s.source_id for s in sources] == ["ok"]


def test_load_sources_can_fail_hard(tmp_path: Path):
    _write(
        tmp_path / "bad.json",
        _raw(authorization={"authorized": False, "consent_reference": ""}),
    )
    with pytest.raises(AuthorizationError):
        load_sources(tmp_path, skip_unauthorized=False)
