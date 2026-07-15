"""The offline training pipeline (Module 18).

Orchestrates: gather authorized transcript sources → analyse pacing + vocabulary →
produce an anonymized :class:`StyleProfile` artifact. It is a **standalone offline
tool**: it takes no event bus, is never started by the live :class:`Application`,
and only ever *exports a profile* the operator can review. It can suggest pacing
defaults for the Commentary Director, but never applies them itself — a human
decides whether to adopt them.
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_caster.core.logging import get_logger
from ai_caster.training.analysis import compute_pacing, compute_vocabulary
from ai_caster.training.guardrails import POLICY, ensure_authorized, reject_audio
from ai_caster.training.ingest import load_sources
from ai_caster.training.models import StyleProfile, TrainingSource

_log = get_logger("training.pipeline")


class TrainingPipeline:
    """Builds a :class:`StyleProfile` from authorized transcripts, offline."""

    def __init__(self, *, top_n: int = 25, min_term_count: int = 2) -> None:
        self._sources: list[TrainingSource] = []
        self._top_n = top_n
        self._min_term_count = min_term_count

    @property
    def policy(self) -> str:
        return POLICY

    @property
    def sources(self) -> list[TrainingSource]:
        return list(self._sources)

    # ------------------------------------------------------------------ #
    def add_source(self, source: TrainingSource) -> None:
        """Add one already-parsed source (re-checked against the guardrails)."""
        ensure_authorized(source)
        self._sources.append(source)

    def add_directory(self, directory: Path, *, skip_unauthorized: bool = True) -> int:
        """Load every authorized transcript in ``directory``. Returns the count added."""
        loaded = load_sources(directory, skip_unauthorized=skip_unauthorized)
        self._sources.extend(loaded)
        return len(loaded)

    def add_media(
        self,
        source,
        *,
        authorization,
        transcriber,
        language: str = "en",
        source_id: str | None = None,
    ):
        """Transcribe an authorized recording and add it as a source.

        A thin wrapper over :func:`~ai_caster.training.media.transcribe_media`; the
        recording is turned into an anonymized transcript (no voice model, generic
        role) before it enters the general-style analysis.
        """
        from ai_caster.training.media import transcribe_media

        parsed = transcribe_media(
            source, transcriber, authorization, language=language, source_id=source_id
        )
        self._sources.append(parsed)
        return parsed

    def run(self) -> StyleProfile:
        """Analyse the gathered sources into a single aggregate style profile."""
        language = self._sources[0].language if self._sources else "en"
        total_segments = sum(len(s.segments) for s in self._sources)
        profile = StyleProfile(
            num_sources=len(self._sources),
            total_segments=total_segments,
            language=language,
            pacing=compute_pacing(self._sources),
            vocabulary=compute_vocabulary(
                self._sources, top_n=self._top_n, min_count=self._min_term_count
            ),
        )
        _log.info(
            "Training complete: %d sources, %d segments analysed.",
            profile.num_sources,
            profile.total_segments,
        )
        return profile

    # ------------------------------------------------------------------ #
    @staticmethod
    def save_profile(profile: StyleProfile, path: Path) -> None:
        """Write the profile artifact as JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")

    @staticmethod
    def suggested_director_settings(profile: StyleProfile) -> dict:
        """Suggest Commentary Director pacing values derived from the profile.

        These are *suggestions for a human to review*, not applied automatically —
        the training tool never reaches into the live engine. The minimum speech
        gap is derived from the observed average inter-line silence, clamped to a
        sane broadcast range.
        """
        gap_ms = int(round(profile.pacing.avg_gap_seconds * 1000))
        gap_ms = max(200, min(2000, gap_ms))
        return {
            "min_speech_gap_ms": gap_ms,
            "note": "Suggested from authorized-transcript pacing; review before adopting.",
        }

    @staticmethod
    def summary(profile: StyleProfile) -> str:
        """A short human-readable report of the profile."""
        p, v = profile.pacing, profile.vocabulary
        top = ", ".join(term for term, _ in v.top_terms[:8]) or "—"
        return (
            f"Style profile ({profile.language}) from {profile.num_sources} source(s), "
            f"{profile.total_segments} segments\n"
            f"  Pacing: {p.avg_words_per_line:.1f} words/line, "
            f"{p.words_per_second:.2f} words/sec, {p.lines_per_minute:.1f} lines/min, "
            f"avg gap {p.avg_gap_seconds:.2f}s\n"
            f"  Vocabulary: {v.unique_tokens} unique / {v.tokens_analyzed} tokens, "
            f"TTR {v.type_token_ratio:.2f}, filler {v.filler_ratio * 100:.1f}%\n"
            f"  Common terms: {top}"
        )


def build_source_from_dict(raw: dict) -> TrainingSource:
    """Convenience: guardrail-check + parse a raw source dict."""
    from ai_caster.training.ingest import parse_source

    reject_audio(raw)
    return parse_source(raw)
