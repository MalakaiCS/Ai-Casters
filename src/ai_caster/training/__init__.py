"""Module 18 — Offline Training Pipeline.

A **standalone, offline** analysis tool (not part of the live casting engine). It
learns *general* timing/pacing and generic vocabulary tendencies from **authorized
transcripts** and exports an anonymized style profile.

Its guardrails are the whole point and are enforced at the boundary: transcripts
only (**no audio, so no voice cloning**), authorized + consent-referenced sources
only, speakers anonymized to generic roles, and proper nouns excluded from learned
vocabulary — so **no identifiable individual is modelled or imitated**. The profile
can *suggest* pacing defaults for review; it is never applied automatically.
"""

from ai_caster.training.guardrails import (
    POLICY,
    AudioInputRejected,
    AuthorizationError,
    anonymize_role,
)
from ai_caster.training.ingest import load_source_file, load_sources, parse_source
from ai_caster.training.models import (
    Authorization,
    PacingProfile,
    StyleProfile,
    TrainingSource,
    TranscriptSegment,
    VocabularyProfile,
)
from ai_caster.training.pipeline import TrainingPipeline

__all__ = [
    "POLICY",
    "AudioInputRejected",
    "AuthorizationError",
    "anonymize_role",
    "parse_source",
    "load_source_file",
    "load_sources",
    "Authorization",
    "TranscriptSegment",
    "TrainingSource",
    "PacingProfile",
    "VocabularyProfile",
    "StyleProfile",
    "TrainingPipeline",
]
