"""Speech-to-text for the training pipeline.

Turns an **authorized** audio/video recording into timed transcript segments so
the existing general-style analysis can learn from it. This reads audio only to
produce *text + timing* — it never builds a voice model, stores audio features,
or identifies speakers, so the "no voice cloning / no identity imitation"
guarantee is preserved: every segment is tagged with the generic role
``commentator`` and passes the same anonymization as text sources.

:class:`WhisperTranscriber` uses ``faster-whisper`` (the ``[training]`` extra),
lazy-imported so the package doesn't require it unless transcription is used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ai_caster.core.logging import get_logger
from ai_caster.training.models import TranscriptSegment

_log = get_logger("training.transcribe")


@runtime_checkable
class Transcriber(Protocol):
    """Produces timed transcript segments from a media file."""

    @property
    def name(self) -> str: ...

    def transcribe(self, media_path: Path, *, language: str = "en") -> list[TranscriptSegment]: ...


class WhisperTranscriber:
    """Local speech-to-text via ``faster-whisper``.

    All output segments use the generic ``commentator`` role — the model does not
    (and we do not want it to) attribute speech to an identifiable person.
    """

    name = "whisper"

    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        self._model = None

    def _load(self):  # pragma: no cover - heavy optional dependency
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "Transcription requires faster-whisper. Install the training extra: "
                'pip install "ai-esports-caster[training]"'
            ) from exc
        if self._model is None:
            self._model = WhisperModel(self._model_size)
        return self._model

    def transcribe(self, media_path: Path, *, language: str = "en") -> list[TranscriptSegment]:
        model = self._load()  # pragma: no cover - heavy model run
        segments, _info = model.transcribe(str(media_path), language=language)  # pragma: no cover
        out: list[TranscriptSegment] = []
        for seg in segments:  # pragma: no cover - depends on the model
            text = str(seg.text).strip()
            if text:
                out.append(
                    TranscriptSegment(
                        role="commentator",
                        text=text,
                        start=float(seg.start),
                        end=float(seg.end),
                    )
                )
        return out
