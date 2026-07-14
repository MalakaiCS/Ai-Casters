"""Tests for the training guardrails — the ethical boundary of Module 18."""

from __future__ import annotations

import pytest

from ai_caster.training.guardrails import (
    AudioInputRejected,
    AuthorizationError,
    anonymize_role,
    ensure_authorized,
    is_learnable_token,
    reject_audio,
)
from ai_caster.training.models import Authorization, TrainingSource


# --- no audio / no voice cloning ------------------------------------------- #
def test_reject_audio_top_level():
    with pytest.raises(AudioInputRejected):
        reject_audio({"source_id": "x", "audio_path": "clip.wav"})


def test_reject_audio_in_segment():
    with pytest.raises(AudioInputRejected):
        reject_audio({"segments": [{"text": "hi", "waveform": [0.1, 0.2]}]})


def test_reject_audio_allows_pure_transcript():
    reject_audio({"source_id": "x", "segments": [{"text": "hi", "start": 0, "end": 1}]})


# --- authorization required ------------------------------------------------ #
def test_ensure_authorized_refuses_uncleared():
    source = TrainingSource("s1", Authorization(authorized=False))
    with pytest.raises(AuthorizationError):
        ensure_authorized(source)


def test_ensure_authorized_requires_consent_reference():
    source = TrainingSource("s1", Authorization(authorized=True, consent_reference=""))
    with pytest.raises(AuthorizationError):
        ensure_authorized(source)


def test_ensure_authorized_accepts_valid():
    source = TrainingSource("s1", Authorization(authorized=True, consent_reference="CONSENT-1"))
    ensure_authorized(source)  # no raise


# --- anonymized roles ------------------------------------------------------ #
def test_anonymize_role_maps_generic():
    assert anonymize_role("Play-by-Play") == "play_by_play"
    assert anonymize_role("analyst") == "analyst"
    assert anonymize_role("color") == "analyst"


def test_anonymize_role_unknown_becomes_commentator():
    # A person's name must never survive as a label.
    assert anonymize_role("SomeFamousCaster") == "commentator"


# --- generic vocabulary only ----------------------------------------------- #
def test_learnable_token_drops_proper_nouns_midline():
    # Capitalized mid-sentence => name/team; excluded.
    assert not is_learnable_token("Simple", position=3)
    # Sentence-start capitalization is allowed (it's just a normal word).
    assert is_learnable_token("Amazing", position=0)


def test_learnable_token_drops_nonwords():
    assert not is_learnable_token("s1mple", position=1)  # has a digit
    assert not is_learnable_token("!!!", position=1)


def test_learnable_token_keeps_generic_words():
    assert is_learnable_token("clutch", position=2)
    assert is_learnable_token("the", position=1)
