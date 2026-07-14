"""Data models for the offline training pipeline (Module 18).

The pipeline learns **general** timing/pacing and generic vocabulary tendencies
from *authorized transcripts* — never audio, never a model of an identifiable
person. These models reflect that: a source carries explicit authorization, its
segments are text + timing tagged with a **generic role** (never a real name), and
the exported profile is aggregate statistics only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Authorization:
    """Proof that a recording may be used for training.

    Training refuses any source that is not authorized *and* backed by a consent
    reference — the pipeline never touches un-cleared material.
    """

    authorized: bool = False
    consent_reference: str = ""
    rights_holder: str = ""
    note: str = ""

    @property
    def is_valid(self) -> bool:
        return self.authorized and bool(self.consent_reference)


@dataclass(frozen=True)
class TranscriptSegment:
    """One spoken line: text + timing, tagged with a generic role only."""

    role: str  # generic: "play_by_play" | "analyst" | "commentator"
    text: str
    start: float  # seconds from the recording start
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass(frozen=True)
class TrainingSource:
    """An authorized transcript and its anonymized segments."""

    source_id: str
    authorization: Authorization
    segments: list[TranscriptSegment] = field(default_factory=list)
    language: str = "en"


@dataclass(frozen=True)
class PacingProfile:
    """Aggregate delivery timing — the rhythm, not the words."""

    segments_analyzed: int = 0
    avg_words_per_line: float = 0.0
    avg_line_duration: float = 0.0
    median_line_duration: float = 0.0
    avg_gap_seconds: float = 0.0
    words_per_second: float = 0.0
    lines_per_minute: float = 0.0


@dataclass(frozen=True)
class VocabularyProfile:
    """Aggregate, anonymized vocabulary tendencies (generic terms only)."""

    tokens_analyzed: int = 0
    unique_tokens: int = 0
    type_token_ratio: float = 0.0
    filler_ratio: float = 0.0
    top_terms: list[tuple[str, int]] = field(default_factory=list)
    top_bigrams: list[tuple[str, int]] = field(default_factory=list)


@dataclass(frozen=True)
class StyleProfile:
    """The exportable training artifact: anonymized, aggregate style statistics.

    It describes *how commentary tends to be paced and phrased in general*. It
    contains no audio, no speaker identities and no verbatim signature phrases, so
    it can inform pacing/vocabulary defaults without imitating anyone.
    """

    num_sources: int = 0
    total_segments: int = 0
    language: str = "en"
    pacing: PacingProfile = field(default_factory=PacingProfile)
    vocabulary: VocabularyProfile = field(default_factory=VocabularyProfile)
    generated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return {
            "kind": "ai_caster.style_profile",
            "num_sources": self.num_sources,
            "total_segments": self.total_segments,
            "language": self.language,
            "generated_at": self.generated_at.isoformat(),
            "pacing": {
                "segments_analyzed": self.pacing.segments_analyzed,
                "avg_words_per_line": self.pacing.avg_words_per_line,
                "avg_line_duration": self.pacing.avg_line_duration,
                "median_line_duration": self.pacing.median_line_duration,
                "avg_gap_seconds": self.pacing.avg_gap_seconds,
                "words_per_second": self.pacing.words_per_second,
                "lines_per_minute": self.pacing.lines_per_minute,
            },
            "vocabulary": {
                "tokens_analyzed": self.vocabulary.tokens_analyzed,
                "unique_tokens": self.vocabulary.unique_tokens,
                "type_token_ratio": self.vocabulary.type_token_ratio,
                "filler_ratio": self.vocabulary.filler_ratio,
                "top_terms": [list(t) for t in self.vocabulary.top_terms],
                "top_bigrams": [list(b) for b in self.vocabulary.top_bigrams],
            },
        }
