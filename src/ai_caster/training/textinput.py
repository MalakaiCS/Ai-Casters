"""Turn a **pasted transcript** into training segments, split by casting role.

Two jobs:

* :func:`parse_transcript_text` accepts free text — one line per spoken beat —
  and produces timed :class:`TranscriptSegment` s. A line may be explicitly
  labelled (``PBP:`` / ``Analyst:`` / …); otherwise :func:`classify_role` guesses
  play-by-play vs analyst from the language itself.
* :func:`classify_role` is a light heuristic: play-by-play is short, present-tense
  live action ("he's down!", "ACE!"); analyst is longer, explanatory, past/
  conditional ("the reason that worked is the eco…"). It's a nudge, not a
  linguist — good enough to bucket lines for per-role analysis.

Timing is estimated from word count (there's none in pasted text) so pacing
stats have something sensible to chew on.
"""

from __future__ import annotations

import re

from ai_caster.training.guardrails import anonymize_role
from ai_caster.training.models import TranscriptSegment

# Explicit "Role: line" labels a user might paste.
_LABEL_RE = re.compile(
    r"^\s*(pbp|play[\s-]?by[\s-]?play|analyst|colou?r|caster|commentator|desk)\s*[:\-]\s*(.*)$",
    re.IGNORECASE,
)

# Play-by-play markers: live action, immediacy, hype.
_PBP_WORDS = frozenset(
    {
        "kill",
        "kills",
        "killed",
        "down",
        "dead",
        "headshot",
        "frag",
        "ace",
        "clutch",
        "defuse",
        "defused",
        "plant",
        "planted",
        "boom",
        "wins",
        "takes",
        "gets",
        "double",
        "triple",
        "quad",
        "one",
        "shot",
        "noscope",
        "wallbang",
        "spray",
        "peek",
        "entry",
        "trade",
        "traded",
    }
)

# Analyst markers: explanation, cause, strategy, retrospection.
_ANALYST_WORDS = frozenset(
    {
        "because",
        "since",
        "reason",
        "positioning",
        "economy",
        "eco",
        "strategy",
        "strategic",
        "should",
        "could",
        "would",
        "setup",
        "advantage",
        "control",
        "utility",
        "rotate",
        "rotation",
        "default",
        "execute",
        "mistake",
        "decision",
        "map",
        "structure",
        "momentum",
        "adapt",
        "adjust",
        "consider",
        "typically",
        "usually",
    }
)

_WORDS_PER_SECOND = 2.8


def classify_role(text: str) -> str:
    """Guess ``play_by_play`` or ``analyst`` from a single line's language."""
    lowered = text.lower()
    tokens = re.findall(r"[a-z']+", lowered)
    words = len(tokens)
    token_set = set(tokens)

    pbp = len(token_set & _PBP_WORDS)
    analyst = len(token_set & _ANALYST_WORDS)

    pbp += text.count("!")  # excitement is a play-by-play tell
    if any(t.isupper() and t.isalpha() and len(t) > 1 for t in text.split()):
        pbp += 1  # SHOUTING
    if words <= 8:
        pbp += 1  # short, punchy
    if "?" in text:
        analyst += 1  # rhetorical/analytical questions
    if words >= 16:
        analyst += 1  # long explanatory sentence

    return "play_by_play" if pbp >= analyst else "analyst"


def _role_for_line(line: str) -> tuple[str, str]:
    """Return ``(role, text)`` for one line, honouring an explicit label."""
    match = _LABEL_RE.match(line)
    if match:
        role = anonymize_role(match.group(1))
        text = match.group(2).strip()
        # A generic 'commentator'/'desk' label still gets sorted by content.
        if role == "commentator" and text:
            role = classify_role(text)
        return role, text
    text = line.strip()
    return classify_role(text), text


def parse_transcript_text(text: str) -> list[TranscriptSegment]:
    """Parse pasted transcript text into timed, role-tagged segments."""
    segments: list[TranscriptSegment] = []
    cursor = 0.0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        role, content = _role_for_line(line)
        if not content:
            continue
        words = max(1, len(content.split()))
        duration = max(1.0, words / _WORDS_PER_SECOND)
        start = cursor
        end = start + duration
        segments.append(TranscriptSegment(role=role, text=content, start=start, end=end))
        cursor = end + 0.3  # a small breath between lines
    return segments
