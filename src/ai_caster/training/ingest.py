"""Load authorized transcript sources for training.

A source is a JSON document: authorization metadata plus a list of transcript
segments (role, text, start, end). Every source passes the guardrails on the way
in — audio-bearing sources are refused, unauthorized sources are refused, and
speaker roles are anonymized — so nothing downstream has to re-check.
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_caster.core.logging import get_logger
from ai_caster.training.guardrails import (
    AudioInputRejected,
    AuthorizationError,
    anonymize_role,
    ensure_authorized,
    reject_audio,
)
from ai_caster.training.models import Authorization, TrainingSource, TranscriptSegment

_log = get_logger("training.ingest")


def parse_source(raw: dict) -> TrainingSource:
    """Build a :class:`TrainingSource` from a raw dict, enforcing the guardrails.

    Raises :class:`AudioInputRejected` if it carries audio, or
    :class:`AuthorizationError` if it is not cleared for use.
    """
    reject_audio(raw)

    auth_raw = raw.get("authorization", {})
    authorization = Authorization(
        authorized=bool(auth_raw.get("authorized", False)),
        consent_reference=str(auth_raw.get("consent_reference", "")),
        rights_holder=str(auth_raw.get("rights_holder", "")),
        note=str(auth_raw.get("note", "")),
    )

    segments: list[TranscriptSegment] = []
    for entry in raw.get("segments", []):
        text = str(entry.get("text", "")).strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                role=anonymize_role(str(entry.get("role", "commentator"))),
                text=text,
                start=float(entry.get("start", 0.0)),
                end=float(entry.get("end", 0.0)),
            )
        )

    source = TrainingSource(
        source_id=str(raw.get("source_id", "unknown")),
        authorization=authorization,
        segments=segments,
        language=str(raw.get("language", "en")),
    )
    ensure_authorized(source)
    return source


def load_source_file(path: Path) -> TrainingSource:
    """Load and parse a single transcript JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_source(data)


def load_sources(directory: Path, *, skip_unauthorized: bool = True) -> list[TrainingSource]:
    """Load every ``*.json`` transcript in ``directory``.

    Unauthorized (or audio-bearing) files are skipped with a warning by default,
    so a mixed folder still yields the usable, cleared sources rather than failing
    outright. Pass ``skip_unauthorized=False`` to make any refusal raise.
    """
    directory = Path(directory)
    sources: list[TrainingSource] = []
    for path in sorted(directory.glob("*.json")):
        try:
            sources.append(load_source_file(path))
        except (AudioInputRejected, AuthorizationError, ValueError, OSError) as exc:
            if not skip_unauthorized:
                raise
            _log.warning("Skipping %s: %s", path.name, exc)
    return sources
