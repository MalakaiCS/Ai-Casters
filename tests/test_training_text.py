"""Tests for pasted-transcript parsing, role classification, and per-role analysis."""

from __future__ import annotations

from ai_caster.training.analysis import compute_role_profiles
from ai_caster.training.models import Authorization
from ai_caster.training.pipeline import TrainingPipeline
from ai_caster.training.textinput import classify_role, parse_transcript_text

AUTHORIZED = Authorization(authorized=True, consent_reference="OWN-TXT-2026", rights_holder="Me")


def test_classify_role_play_by_play():
    assert classify_role("HE GETS THE ACE, are you kidding me!") == "play_by_play"
    assert classify_role("first blood, entry frag down") == "play_by_play"


def test_classify_role_analyst():
    assert (
        classify_role(
            "the reason that execute worked is because their economy let them commit "
            "utility to take map control"
        )
        == "analyst"
    )


def test_parse_honours_explicit_labels():
    text = "PBP: he takes the entry\nAnalyst: they had the economy to force here\nWHAT A SHOT!"
    segments = parse_transcript_text(text)
    assert [s.role for s in segments] == ["play_by_play", "analyst", "play_by_play"]
    # Timing is synthesised and strictly increasing.
    assert segments[0].start < segments[1].start < segments[2].start
    # Labels are stripped from the text.
    assert segments[0].text == "he takes the entry"


def test_parse_skips_blank_lines():
    segments = parse_transcript_text("one down\n\n   \nhe clutches it")
    assert len(segments) == 2


def test_pipeline_add_text_and_role_breakdown():
    text = (
        "PBP: he takes the entry frag, first blood!\n"
        "PBP: down goes another, they take the round!\n"
        "Analyst: that worked because they had map control and the economy to commit utility\n"
        "Analyst: their positioning here is the reason the execute is so clean"
    )
    pipeline = TrainingPipeline()
    source = pipeline.add_text(text, authorization=AUTHORIZED)
    assert source in pipeline.sources

    breakdown = pipeline.role_breakdown()
    assert breakdown["play_by_play"]["lines"] == 2
    assert breakdown["analyst"]["lines"] == 2
    # The analyst lines are longer on average than the play-by-play lines.
    assert (
        breakdown["analyst"]["pacing"].avg_words_per_line
        > breakdown["play_by_play"]["pacing"].avg_words_per_line
    )


def test_role_breakdown_classifies_generic_commentator_lines():
    # A single-track source (generic 'commentator' role) still splits by content.
    from ai_caster.training.models import TrainingSource, TranscriptSegment

    src = TrainingSource(
        source_id="yt",
        authorization=AUTHORIZED,
        segments=[
            TranscriptSegment("commentator", "he frags out, triple kill!", 0.0, 2.0),
            TranscriptSegment(
                "commentator",
                "the reason that works is their utility usage and map control on the execute",
                2.0,
                6.0,
            ),
        ],
    )
    breakdown = compute_role_profiles([src])
    assert breakdown["play_by_play"]["lines"] == 1
    assert breakdown["analyst"]["lines"] == 1
