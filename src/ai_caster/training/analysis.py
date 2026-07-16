"""Pure analysis functions over authorized transcript segments.

These compute *aggregate* pacing and vocabulary statistics — the rhythm and the
generic word distribution of commentary in general. Everything here is a pure
function of the (already anonymized, already authorized) segments, so it is
deterministic and fully unit-tested. No function here can reach audio or identity;
that was excluded at ingest.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from ai_caster.training.guardrails import FILLER_WORDS, is_learnable_token
from ai_caster.training.models import (
    Authorization,
    PacingProfile,
    TrainingSource,
    TranscriptSegment,
    VocabularyProfile,
)

# A throwaway authorization for internal analysis-only source wrappers (already
# authorized upstream; never re-checked or persisted).
_INTERNAL_AUTH = Authorization(authorized=True, consent_reference="internal")


def _gaps_within_source(segments: list[TranscriptSegment]) -> list[float]:
    """Silence between consecutive lines in one source (never negative)."""
    ordered = sorted(segments, key=lambda s: s.start)
    gaps = []
    for prev, nxt in zip(ordered, ordered[1:], strict=False):
        gaps.append(max(0.0, nxt.start - prev.end))
    return gaps


def compute_pacing(sources: list[TrainingSource]) -> PacingProfile:
    """Aggregate delivery timing across all sources."""
    durations: list[float] = []
    word_counts: list[int] = []
    gaps: list[float] = []
    total_words = 0
    total_speaking = 0.0

    for source in sources:
        for segment in source.segments:
            durations.append(segment.duration)
            word_counts.append(segment.word_count)
            total_words += segment.word_count
            total_speaking += segment.duration
        gaps.extend(_gaps_within_source(source.segments))

    if not durations:
        return PacingProfile()

    durations_arr = np.array(durations, dtype=float)
    words_arr = np.array(word_counts, dtype=float)
    # Wall-clock span estimate: speaking time + inter-line silence.
    span = total_speaking + float(np.sum(gaps)) if gaps else total_speaking
    words_per_second = total_words / total_speaking if total_speaking > 0 else 0.0
    lines_per_minute = (len(durations) / span * 60.0) if span > 0 else 0.0

    return PacingProfile(
        segments_analyzed=len(durations),
        avg_words_per_line=float(np.mean(words_arr)),
        avg_line_duration=float(np.mean(durations_arr)),
        median_line_duration=float(np.median(durations_arr)),
        avg_gap_seconds=float(np.mean(gaps)) if gaps else 0.0,
        words_per_second=words_per_second,
        lines_per_minute=lines_per_minute,
    )


def _tokenize(text: str) -> list[str]:
    """Lowercased, learnable tokens only (proper nouns / non-words dropped)."""
    kept = []
    for position, raw in enumerate(text.split()):
        cleaned = raw.strip(".,!?;:\"'()[]-")
        if cleaned and is_learnable_token(cleaned, position=position):
            kept.append(cleaned.lower())
    return kept


def compute_vocabulary(
    sources: list[TrainingSource], *, top_n: int = 25, min_count: int = 2
) -> VocabularyProfile:
    """Aggregate generic vocabulary tendencies.

    Only terms appearing at least ``min_count`` times are surfaced, so the profile
    reflects *common* language rather than one-off phrasing — another layer keeping
    it generic and non-identifying.
    """
    unigrams: Counter[str] = Counter()
    bigrams: Counter[str] = Counter()
    total_tokens = 0
    filler = 0

    for source in sources:
        for segment in source.segments:
            tokens = _tokenize(segment.text)
            total_tokens += len(tokens)
            for token in tokens:
                unigrams[token] += 1
                if token in FILLER_WORDS:
                    filler += 1
            for a, b in zip(tokens, tokens[1:], strict=False):
                bigrams[f"{a} {b}"] += 1

    if total_tokens == 0:
        return VocabularyProfile()

    common_terms = [(t, c) for t, c in unigrams.most_common() if c >= min_count][:top_n]
    common_bigrams = [(b, c) for b, c in bigrams.most_common() if c >= min_count][:top_n]

    return VocabularyProfile(
        tokens_analyzed=total_tokens,
        unique_tokens=len(unigrams),
        type_token_ratio=len(unigrams) / total_tokens,
        filler_ratio=filler / total_tokens,
        top_terms=common_terms,
        top_bigrams=common_bigrams,
    )


def _segments_by_role(sources: list[TrainingSource]) -> dict[str, list[TranscriptSegment]]:
    """Bucket every segment into play-by-play vs analyst.

    Explicit ``play_by_play`` / ``analyst`` roles are taken as-is; a generic
    ``commentator`` line is sorted by its own language so a single-track source
    (e.g. YouTube captions) still yields a per-role split.
    """
    from ai_caster.training.textinput import classify_role

    buckets: dict[str, list[TranscriptSegment]] = {"play_by_play": [], "analyst": []}
    for source in sources:
        for segment in source.segments:
            role = segment.role
            if role not in ("play_by_play", "analyst"):
                role = classify_role(segment.text)
            buckets[role].append(segment)
    return buckets


def compute_role_profiles(
    sources: list[TrainingSource], *, top_n: int = 15, min_count: int = 2
) -> dict[str, dict]:
    """Per-role pacing + vocabulary — "what's relevant for PBP vs analytical".

    Returns ``{"play_by_play": {...}, "analyst": {...}}`` where each value has the
    line count, a :class:`PacingProfile` and a :class:`VocabularyProfile`, so the
    UI can show how the two roles differ (PBP: short/fast/hype terms; analyst:
    longer/slower/strategy terms).
    """
    buckets = _segments_by_role(sources)
    out: dict[str, dict] = {}
    for role, segments in buckets.items():
        # Wrap the bucket's segments in one throwaway source for the analyzers.
        holder = TrainingSource(source_id=f"role:{role}", authorization=_INTERNAL_AUTH)
        holder.segments.extend(segments)
        out[role] = {
            "lines": len(segments),
            "pacing": compute_pacing([holder]),
            "vocabulary": compute_vocabulary([holder], top_n=top_n, min_count=min_count),
        }
    return out
