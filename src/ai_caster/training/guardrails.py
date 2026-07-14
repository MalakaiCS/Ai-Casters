"""The ethical guardrails that define what this pipeline will and won't do.

These are not incidental checks — they are the point. The master specification is
explicit: the training pipeline performs *offline analysis of authorized
recordings for general timing/pacing/vocabulary learning*, with **no voice cloning
and no imitation of identifiable individuals**. Every constraint below enforces
that at the boundary, so the rest of the pipeline is structurally incapable of
crossing it:

* **Transcripts only, never audio.** :func:`reject_audio` refuses any source that
  carries audio/voice data. Without audio there is nothing to clone.
* **Authorized material only.** :func:`ensure_authorized` refuses any source that
  is not explicitly authorized and backed by a consent reference.
* **Generic roles, never identities.** :func:`anonymize_role` collapses a speaker
  to a generic role; personal names never enter the pipeline as labels.
* **Generic vocabulary only.** :func:`is_learnable_token` drops proper nouns
  (player/team/caster names) and non-words, so learning captures common connective
  language and pacing — not a person's signature phrases.
"""

from __future__ import annotations

POLICY = (
    "Offline analysis of AUTHORIZED transcripts for general timing, pacing and "
    "generic vocabulary only. No audio is ingested; no voice is cloned; no "
    "identifiable individual is modelled or imitated. Speakers are anonymized to "
    "generic roles and proper nouns are excluded from learned vocabulary."
)

# Keys that would indicate raw audio / voice data — always refused.
_AUDIO_KEYS = frozenset(
    {"audio", "audio_path", "waveform", "samples", "voice", "voiceprint", "wav", "mp3"}
)

# The only speaker labels the pipeline keeps. Anything else becomes "commentator".
_GENERIC_ROLES = {
    "play_by_play": "play_by_play",
    "play-by-play": "play_by_play",
    "pbp": "play_by_play",
    "analyst": "analyst",
    "colour": "analyst",
    "color": "analyst",
    "commentator": "commentator",
    "caster": "commentator",
}

# Common filler words, tracked as an aggregate ratio (generic, not identifying).
FILLER_WORDS = frozenset(
    {"um", "uh", "er", "ah", "like", "so", "well", "yeah", "okay", "right", "you", "know"}
)


class AuthorizationError(RuntimeError):
    """Raised when a source is not cleared for training use."""


class AudioInputRejected(RuntimeError):
    """Raised when a source carries audio/voice data (transcript-only pipeline)."""


def reject_audio(raw: dict) -> None:
    """Refuse any source dict that carries audio/voice data.

    This is what makes voice cloning structurally impossible: the pipeline only
    ever sees text, so there is no signal to reconstruct a voice from.
    """
    present = _AUDIO_KEYS.intersection(raw.keys())
    if present:
        raise AudioInputRejected(
            "Training accepts transcripts only; audio/voice fields are refused "
            f"(found: {', '.join(sorted(present))}). No voice is ever ingested or cloned."
        )
    for segment in raw.get("segments", []):
        if isinstance(segment, dict) and _AUDIO_KEYS.intersection(segment.keys()):
            raise AudioInputRejected("A transcript segment carried audio data; refused.")


def ensure_authorized(source) -> None:
    """Refuse a source that is not authorized + consent-referenced."""
    if not source.authorization.is_valid:
        raise AuthorizationError(
            f"Source {source.source_id!r} is not authorized for training "
            "(needs authorized=true and a consent_reference). Refusing to use it."
        )


def anonymize_role(role: str) -> str:
    """Collapse any speaker label to a generic role — never a personal identity."""
    return _GENERIC_ROLES.get(role.strip().lower(), "commentator")


def is_learnable_token(token: str, *, position: int) -> bool:
    """Whether a raw token may enter the learned vocabulary.

    Drops non-alphabetic tokens and proper nouns (a token Capitalized mid-line is
    almost always a player/team/caster name), so identifiable names are excluded
    and only generic, common language is learned.
    """
    if not token.isalpha():
        return False
    if len(token) == 1 and token.lower() not in {"a", "i"}:
        return False
    # Capitalized mid-sentence => proper noun (name); exclude it.
    if position > 0 and token[0].isupper():
        return False
    return True
