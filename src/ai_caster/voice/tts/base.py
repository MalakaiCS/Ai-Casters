"""The text-to-speech engine interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai_caster.voice.audio import AudioClip


@runtime_checkable
class TTSEngine(Protocol):
    """Synthesises speech audio from text."""

    @property
    def name(self) -> str: ...

    @property
    def sample_rate(self) -> int: ...

    def synthesize(self, text: str, voice_id: str = "") -> AudioClip: ...
