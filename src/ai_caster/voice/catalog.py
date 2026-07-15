"""A small, curated catalogue of voices the UI can offer per channel.

The engine accepts *any* voice id (see :class:`VoiceChannelSettings.voice_id`),
but a picker is far friendlier than a raw id field. This module lists a handful
of well-known ElevenLabs stock voices — grouped loosely by how they suit
play-by-play (energetic) versus analyst (measured) — plus a ``Custom…`` sentinel
so an operator can still paste any voice id they own.

These ids are ElevenLabs' public stock voices; using them requires the
operator's own ElevenLabs API key. Nothing here embeds a key or clones a person.
"""

from __future__ import annotations

from dataclasses import dataclass

CUSTOM_LABEL = "Custom…"


@dataclass(frozen=True)
class VoiceOption:
    """One selectable voice: a friendly name, its id, and a short descriptor."""

    name: str
    voice_id: str
    description: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} — {self.description}" if self.description else self.name


# ElevenLabs stock voices (public voice ids). Descriptions are a rough guide to
# which broadcast role each tends to suit.
ELEVENLABS_VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("Josh", "TxGEqnHWrfWFTfGW9XjX", "energetic play-by-play"),
    VoiceOption("Adam", "pNInz6obpgDQGcFmaJgB", "deep, punchy play-by-play"),
    VoiceOption("Antoni", "ErXwobaYiN019PkySvjV", "warm, versatile"),
    VoiceOption("Arnold", "VR6AewLTigWG4xSOukaG", "bold, hype"),
    VoiceOption("Sam", "yoZ06aMxZJJ28mfd3POQ", "measured analyst"),
    VoiceOption("Rachel", "21m00Tcm4TlvDq8ikWAM", "calm, clear analyst"),
    VoiceOption("Bella", "EXAVITQu4vr4xnSDxMaL", "bright, expressive"),
    VoiceOption("Elli", "MF3mGyEYCf7vzuXFRHrX", "youthful, lively"),
    VoiceOption("Domi", "AZnzlk1XvdvUeBnXmlld", "confident, strong"),
)

# Sensible defaults so the two voices sound distinct out of the box.
DEFAULT_PLAY_BY_PLAY = ELEVENLABS_VOICES[0]  # Josh
DEFAULT_ANALYST = ELEVENLABS_VOICES[4]  # Sam


def elevenlabs_voice(voice_id: str) -> VoiceOption | None:
    """Return the catalogue entry for ``voice_id``, or None if it isn't listed."""
    for option in ELEVENLABS_VOICES:
        if option.voice_id == voice_id:
            return option
    return None


def voice_name(voice_id: str) -> str:
    """A friendly name for a voice id (falls back to the id itself)."""
    option = elevenlabs_voice(voice_id)
    return option.name if option else (voice_id or "engine default")


TTS_ENGINES: tuple[tuple[str, str], ...] = (
    ("elevenlabs", "ElevenLabs (production voices)"),
    ("system", "System voice (offline, pyttsx3)"),
    ("synthetic", "Synthetic (offline test tone)"),
)

ELEVENLABS_MODELS: tuple[tuple[str, str], ...] = (
    ("eleven_turbo_v2_5", "Turbo v2.5 — low latency (recommended)"),
    ("eleven_flash_v2_5", "Flash v2.5 — lowest latency"),
    ("eleven_multilingual_v2", "Multilingual v2 — highest quality"),
)
