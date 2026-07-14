"""A single, fully independent voice channel.

Each channel owns its queue, worker thread, TTS engine, DSP chain, output sink,
volume/mute, latency (broadcast delay) and interruption logic — nothing is shared
with the other channel, per the spec's "two completely independent voices".
Synthesis and playback happen on the worker thread so they never block the bus.

Interruption (speech cancellation): a higher-priority line can pre-empt whatever
is speaking. :meth:`speak` with ``interrupt=True`` drains the queue and signals
the worker to abort the in-flight line before it reaches the device.
"""

from __future__ import annotations

import queue
import threading

from ai_caster.core.logging import get_logger
from ai_caster.voice.audio import ChannelDSP
from ai_caster.voice.sink import AudioSink
from ai_caster.voice.tts.base import TTSEngine

_log = get_logger("voice.channel")

_SENTINEL = object()


class VoiceChannel:
    """One independent voice pipeline: queue → TTS → DSP → latency → sink."""

    def __init__(
        self,
        name: str,
        tts: TTSEngine,
        dsp: ChannelDSP,
        sink: AudioSink,
        *,
        voice_id: str = "",
        latency_ms: int = 0,
        monitor=None,
        enabled: bool = True,
        queue_size: int = 8,
    ) -> None:
        self._name = name
        self._tts = tts
        self._dsp = dsp
        self._sink = sink
        self._voice_id = voice_id
        self._latency = max(0.0, latency_ms / 1000.0)
        self._monitor = monitor
        self._enabled = enabled

        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._spoken = 0

    # ------------------------------------------------------------------ #
    @property
    def name(self) -> str:
        return self._name

    @property
    def dsp(self) -> ChannelDSP:
        return self._dsp

    @property
    def spoken_count(self) -> int:
        return self._spoken

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def pending(self) -> int:
        return self._queue.qsize()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_volume(self, volume: float) -> None:
        self._dsp.volume = volume

    def set_muted(self, muted: bool) -> None:
        self._dsp.muted = muted

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if self.is_running:
            return
        self._sink.open()
        self._thread = threading.Thread(
            target=self._worker, name=f"voice-{self._name}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._interrupt()
            try:
                self._queue.put_nowait(_SENTINEL)
            except queue.Full:  # pragma: no cover - drained above
                pass
            self._thread.join(timeout=3.0)
        self._thread = None
        self._sink.close()

    # ------------------------------------------------------------------ #
    def speak(self, text: str, *, interrupt: bool = False) -> None:
        """Queue a line for speech. ``interrupt`` pre-empts the current line."""
        if not self._enabled or not text:
            return
        if interrupt:
            self._interrupt()
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            # Drop the oldest pending line to stay current.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(text)
            except (queue.Empty, queue.Full):  # pragma: no cover - race
                pass

    def _interrupt(self) -> None:
        self._cancel.set()
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is _SENTINEL:  # keep a stop request in the queue
                try:
                    self._queue.put_nowait(_SENTINEL)
                except queue.Full:  # pragma: no cover
                    pass
                break

    # ------------------------------------------------------------------ #
    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                break
            # A fresh line starts clean; a cancel set for a previous line no
            # longer applies once we've moved past it.
            self._cancel.clear()
            try:
                clip = self._tts.synthesize(item, self._voice_id)
            except Exception:  # noqa: BLE001 - never let one line kill the channel
                _log.exception("TTS failed on channel %s", self._name)
                continue
            if self._cancel.is_set():
                continue
            processed = self._dsp.process(clip)
            # Broadcast latency, interruptibly.
            if self._latency > 0 and self._cancel.wait(self._latency):
                continue
            try:
                self._sink.write(processed)
                if self._monitor is not None:
                    self._monitor.submit(self._name, processed)
            except Exception:  # noqa: BLE001 - device errors shouldn't crash the show
                _log.exception("Audio output failed on channel %s", self._name)
                continue
            self._spoken += 1
