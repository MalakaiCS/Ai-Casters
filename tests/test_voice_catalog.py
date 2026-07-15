"""Tests for the voice catalogue and live voice switching."""

from __future__ import annotations

from ai_caster.voice.catalog import (
    DEFAULT_ANALYST,
    DEFAULT_PLAY_BY_PLAY,
    ELEVENLABS_VOICES,
    elevenlabs_voice,
    voice_name,
)


def test_catalog_entries_are_unique_and_have_ids():
    ids = [v.voice_id for v in ELEVENLABS_VOICES]
    assert len(ids) == len(set(ids))  # no duplicate ids
    assert all(v.voice_id and v.name for v in ELEVENLABS_VOICES)


def test_defaults_are_distinct():
    assert DEFAULT_PLAY_BY_PLAY.voice_id != DEFAULT_ANALYST.voice_id


def test_lookup_by_id():
    option = ELEVENLABS_VOICES[0]
    assert elevenlabs_voice(option.voice_id) is option
    assert elevenlabs_voice("does-not-exist") is None


def test_voice_name_falls_back_to_id_then_default():
    assert voice_name(ELEVENLABS_VOICES[0].voice_id) == ELEVENLABS_VOICES[0].name
    assert voice_name("unknown-id") == "unknown-id"
    assert voice_name("") == "engine default"
