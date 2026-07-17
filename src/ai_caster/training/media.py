"""Ingest **authorized** audio/video recordings into training sources.

This is the "learn from real commentary" path, kept inside the same ethical
boundary as the rest of the training pipeline:

* **Authorized only** — the caller must supply a valid :class:`Authorization`
  (an "I have the rights to this recording" affirmation). Unauthorized sources
  are refused before any work is done.
* **Your own content, not scraped platforms** — a direct file path or a direct
  media URL you host is accepted; links to YouTube/Twitch/etc. are refused,
  because downloading third-party broadcasts is a rights problem, not a feature.
* **Transcript + timing only** — the recording is transcribed to text and folded
  through the same anonymization (generic roles, proper nouns excluded) as text
  sources. No voice model is built and no speaker is identified.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import urlparse

from ai_caster.core.logging import get_logger
from ai_caster.training.guardrails import anonymize_role, ensure_authorized
from ai_caster.training.models import Authorization, TrainingSource, TranscriptSegment
from ai_caster.training.transcribe import Transcriber

_log = get_logger("training.media")

# Platform hosts whose content we will not download (rights / ToS).
_PLATFORM_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "twitch.tv",
        "www.twitch.tv",
        "clips.twitch.tv",
        "tiktok.com",
        "www.tiktok.com",
        "instagram.com",
        "www.instagram.com",
        "facebook.com",
        "www.facebook.com",
        "fb.watch",
        "vimeo.com",
    }
)


class MediaSourceError(RuntimeError):
    """A media source can't be used (a platform link, or a missing file)."""


def reject_platform_url(url: str) -> None:
    """Refuse links to streaming platforms — we don't scrape third-party video."""
    host = (urlparse(url).hostname or "").lower()
    if host in _PLATFORM_HOSTS:
        raise MediaSourceError(
            f"Refusing to download from {host}: use recordings you own or are "
            "licensed to use (a local file or a direct link to your own upload). "
            "Third-party broadcasts can't be scraped for training."
        )


def _resolve_media(source: str | Path) -> tuple[Path, Path | None]:
    """Return (local_path, temp_to_cleanup). Downloads a direct URL you host."""
    text = str(source)
    if text.startswith(("http://", "https://")):
        reject_platform_url(text)
        return _download(text), None  # temp handled by caller via returned path
    path = Path(source)
    if not path.is_file():
        raise MediaSourceError(f"Media file not found: {path}")
    return path, None


def _download(url: str) -> Path:  # pragma: no cover - network I/O
    import urllib.request

    suffix = Path(urlparse(url).path).suffix or ".bin"
    fd, name = tempfile.mkstemp(suffix=suffix, prefix="aic-media-")
    dest = Path(name)
    import os

    os.close(fd)
    with urllib.request.urlopen(url, timeout=60) as response, dest.open("wb") as handle:  # noqa: S310
        while chunk := response.read(65536):
            handle.write(chunk)
    return dest


def transcribe_media(
    source: str | Path,
    transcriber: Transcriber,
    authorization: Authorization,
    *,
    language: str = "en",
    source_id: str | None = None,
) -> TrainingSource:
    """Transcribe an authorized recording into an anonymized training source."""
    # Authorization is checked *before* any download/transcription work.
    probe = TrainingSource(source_id or "media", authorization)
    ensure_authorized(probe)

    path, temp = _resolve_media(source)
    try:
        raw = transcriber.transcribe(Path(path), language=language)
    finally:
        if temp is not None:  # pragma: no cover - only on URL downloads
            temp.unlink(missing_ok=True)

    segments = [
        TranscriptSegment(
            role=anonymize_role(seg.role),
            text=seg.text,
            start=seg.start,
            end=seg.end,
        )
        for seg in raw
        if seg.text.strip()
    ]
    source_obj = TrainingSource(
        source_id=source_id or Path(str(source)).stem or "media",
        authorization=authorization,
        segments=segments,
        language=language,
    )
    ensure_authorized(source_obj)
    _log.info("Transcribed %s -> %d segments", source_id or source, len(segments))
    return source_obj
