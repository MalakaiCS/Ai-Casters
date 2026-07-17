"""Tests for the pacing and vocabulary analysis functions."""

from __future__ import annotations

from ai_caster.training.analysis import compute_pacing, compute_vocabulary
from ai_caster.training.models import Authorization, TrainingSource, TranscriptSegment

_AUTH = Authorization(authorized=True, consent_reference="C-1")


def _source(segments: list[TranscriptSegment], sid: str = "s") -> TrainingSource:
    return TrainingSource(sid, _AUTH, segments=segments)


def test_pacing_aggregates_timing():
    segments = [
        TranscriptSegment("play_by_play", "one two three four", 0.0, 2.0),  # 4 words / 2s
        TranscriptSegment("analyst", "five six", 3.0, 4.0),  # 2 words / 1s, gap 1.0s
    ]
    pacing = compute_pacing([_source(segments)])
    assert pacing.segments_analyzed == 2
    assert pacing.avg_words_per_line == 3.0
    assert pacing.avg_line_duration == 1.5
    assert abs(pacing.avg_gap_seconds - 1.0) < 1e-9
    # 6 words over 3s of speaking time.
    assert abs(pacing.words_per_second - 2.0) < 1e-9


def test_pacing_empty_is_zeroed():
    assert compute_pacing([]).segments_analyzed == 0


def test_vocabulary_drops_proper_nouns_and_nonwords():
    # "Simple" (name, mid-line) and "AWP" (mid-line caps) and "s1mple" must not appear.
    segments = [
        TranscriptSegment("play_by_play", "the clutch from Simple with the AWP", 0.0, 2.0),
        TranscriptSegment("analyst", "the clutch was the clutch again", 2.0, 4.0),
    ]
    vocab = compute_vocabulary([_source(segments)], min_count=2)
    terms = dict(vocab.top_terms)
    assert "simple" not in terms
    assert "awp" not in terms
    assert terms.get("clutch", 0) >= 2  # generic term survives
    assert terms.get("the", 0) >= 2


def test_vocabulary_min_count_filters_rare_terms():
    segments = [TranscriptSegment("analyst", "unique words appear once only here", 0.0, 2.0)]
    vocab = compute_vocabulary([_source(segments)], min_count=2)
    assert vocab.top_terms == []  # nothing repeats
    assert vocab.tokens_analyzed > 0
    assert vocab.type_token_ratio > 0.0


def test_vocabulary_tracks_filler_ratio():
    segments = [TranscriptSegment("analyst", "so you know the play", 0.0, 2.0)]
    vocab = compute_vocabulary([_source(segments)], min_count=1)
    # "so", "you", "know" are fillers out of 5 tokens.
    assert abs(vocab.filler_ratio - 3 / 5) < 1e-9


def test_vocabulary_bigrams():
    segments = [
        TranscriptSegment("analyst", "on the bomb site on the bomb site", 0.0, 2.0),
    ]
    vocab = compute_vocabulary([_source(segments)], min_count=2)
    bigrams = dict(vocab.top_bigrams)
    assert bigrams.get("on the", 0) >= 2
