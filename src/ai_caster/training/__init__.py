"""Module 18 — Offline Training Pipeline.

A **standalone, offline** analysis tool (not part of the live casting engine). It
learns *general* timing/pacing and generic vocabulary tendencies from **authorized
recordings/transcripts** and exports an anonymized style profile.

Its guardrails are the whole point and are enforced at the boundary: **authorized
+ consent-referenced sources only**; audio/video is used solely to derive a
**transcript + timing** (no voice model is built, no speaker identified, and
third-party platform links are refused); speakers are anonymized to generic roles;
and proper nouns are excluded from learned vocabulary — so **no identifiable
individual is modelled or imitated**. The profile can *suggest* pacing defaults for
review; it is never applied automatically.
"""

from ai_caster.training.guardrails import (
    POLICY,
    AudioInputRejected,
    AuthorizationError,
    anonymize_role,
)
from ai_caster.training.ingest import load_source_file, load_sources, parse_source
from ai_caster.training.media import MediaSourceError, reject_platform_url, transcribe_media
from ai_caster.training.models import (
    Authorization,
    PacingProfile,
    StyleProfile,
    TrainingSource,
    TranscriptSegment,
    VocabularyProfile,
)
from ai_caster.training.pipeline import TrainingPipeline
from ai_caster.training.transcribe import Transcriber, WhisperTranscriber
from ai_caster.training.youtube import (
    YouTubeTranscriptError,
    extract_video_id,
    fetch_youtube_transcript,
)

__all__ = [
    "POLICY",
    "AudioInputRejected",
    "AuthorizationError",
    "anonymize_role",
    "parse_source",
    "load_source_file",
    "load_sources",
    "transcribe_media",
    "reject_platform_url",
    "MediaSourceError",
    "Transcriber",
    "WhisperTranscriber",
    "fetch_youtube_transcript",
    "extract_video_id",
    "YouTubeTranscriptError",
    "Authorization",
    "TranscriptSegment",
    "TrainingSource",
    "PacingProfile",
    "VocabularyProfile",
    "StyleProfile",
    "TrainingPipeline",
]
