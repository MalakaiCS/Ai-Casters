"""Fetch a YouTube video's **caption transcript** for training.

This is the "easier training" path: paste a link and learn general pacing and
vocabulary from the video's captions. It stays inside the same ethical boundary
as the rest of the pipeline:

* **Transcript only.** Only the existing caption text + timing is read — no audio
  or video is ever downloaded, so no voice is captured and nothing can be cloned.
* **Authorized only.** The caller must affirm they have the rights to the content
  (their own channel, or licensed / Creative-Commons material). We do not decide
  that for them, but the pipeline refuses sources without an authorization.
* **General style only.** Captions run through the same anonymization (generic
  ``commentator`` role, proper nouns excluded downstream) as every other source.

Uses ``youtube-transcript-api`` (the ``[training]`` extra), lazy-imported so the
package doesn't require it unless YouTube captions are actually used.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from ai_caster.core.logging import get_logger
from ai_caster.training.models import TranscriptSegment

_log = get_logger("training.youtube")


class YouTubeTranscriptError(RuntimeError):
    """A YouTube link couldn't be turned into a transcript."""


def extract_video_id(url_or_id: str) -> str:
    """Pull the 11-char video id out of a YouTube URL (or accept a bare id)."""
    text = url_or_id.strip()
    # Already a bare id.
    if "/" not in text and "?" not in text and len(text) >= 11:
        return text[:11] if len(text) > 11 else text
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
            vid = parsed.path.split("/")[2]
        else:
            vid = parse_qs(parsed.query).get("v", [""])[0]
    else:
        vid = ""
    if not vid:
        raise YouTubeTranscriptError(f"Couldn't find a YouTube video id in {url_or_id!r}.")
    return vid


def _to_segments(raw: list[dict]) -> list[TranscriptSegment]:
    """Map youtube-transcript-api rows to anonymized transcript segments."""
    segments: list[TranscriptSegment] = []
    for row in raw:
        text = str(row.get("text", "")).strip()
        if not text or text == "[Music]":
            continue
        start = float(row.get("start", 0.0))
        end = start + float(row.get("duration", 0.0))
        segments.append(TranscriptSegment(role="commentator", text=text, start=start, end=end))
    return segments


def fetch_youtube_transcript(
    url: str, *, languages: tuple[str, ...] = ("en",)
) -> list[TranscriptSegment]:
    """Fetch ``url``'s caption transcript as anonymized segments.

    Raises :class:`YouTubeTranscriptError` if captions can't be retrieved (no
    captions, disabled, or the extra isn't installed).
    """
    video_id = extract_video_id(url)
    try:  # pragma: no cover - network + optional dependency
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise YouTubeTranscriptError(
            "YouTube captions need the training extra: "
            'pip install "ai-esports-caster[training]"'
        ) from exc
    try:  # pragma: no cover - network I/O
        raw = YouTubeTranscriptApi.get_transcript(video_id, languages=list(languages))
    except Exception as exc:  # noqa: BLE001 - library raises several types
        raise YouTubeTranscriptError(
            f"Couldn't get captions for {video_id}: {exc}. The video may have no "
            "captions, or they're disabled."
        ) from exc
    segments = _to_segments(raw)
    _log.info("Fetched %d caption segments from YouTube %s", len(segments), video_id)
    return segments
