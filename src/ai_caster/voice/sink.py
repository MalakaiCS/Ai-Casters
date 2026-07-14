"""Audio output sinks.

A sink is where a channel's processed audio goes — a Windows/OS output device in
production, or the offline :class:`NullSink` (which records what it received) in
development and tests. Assigning a different device per channel is what the spec's
routing example needs (caster → Cable A, analyst → Cable B, monitor → headphones).
"""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable

from ai_caster.core.logging import get_logger
from ai_caster.voice.audio import AudioClip

_log = get_logger("voice.sink")


@runtime_checkable
class AudioSink(Protocol):
    """Consumes audio clips for playback."""

    @property
    def name(self) -> str: ...

    def open(self) -> None: ...

    def write(self, clip: AudioClip) -> None: ...

    def close(self) -> None: ...


class NullSink:
    """Discards audio but records what it received (for dev/tests)."""

    def __init__(self, name: str = "null") -> None:
        self._name = name
        self._lock = threading.Lock()
        self.clips_written = 0
        self.samples_written = 0
        self.last_clip: AudioClip | None = None

    @property
    def name(self) -> str:
        return self._name

    def open(self) -> None:
        return None

    def write(self, clip: AudioClip) -> None:
        with self._lock:
            self.clips_written += 1
            self.samples_written += int(clip.samples.size)
            self.last_clip = clip

    def close(self) -> None:
        return None


class SoundDeviceSink:
    """Plays audio to a real output device via ``sounddevice`` (optional)."""

    def __init__(self, device: str = "", sample_rate: int = 24000, name: str = "device") -> None:
        self._device = device or None
        self._sample_rate = sample_rate
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def _sd(self):
        try:
            import sounddevice  # type: ignore
        except ImportError as exc:  # pragma: no cover - only without sounddevice
            raise RuntimeError(
                "Device output requires sounddevice. Install voice extras: "
                'pip install "ai-esports-caster[voice]"'
            ) from exc
        return sounddevice

    def open(self) -> None:
        self._sd()  # fail fast if unavailable

    def write(self, clip: AudioClip) -> None:
        sd = self._sd()
        sd.play(clip.samples, samplerate=clip.sample_rate, device=self._device, blocking=True)

    def close(self) -> None:
        return None


def list_output_devices() -> list[str]:
    """Return output device names, or an empty list if enumeration is unavailable."""
    try:
        import sounddevice  # type: ignore
    except ImportError:
        return []
    try:  # pragma: no cover - depends on host audio stack
        return [
            d["name"] for d in sounddevice.query_devices() if d.get("max_output_channels", 0) > 0
        ]
    except Exception:  # noqa: BLE001 - host audio may be unavailable
        return []
