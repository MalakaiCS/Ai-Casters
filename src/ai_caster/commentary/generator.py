"""A commentary generator for one speaker role.

Subscribes to the Director's directives, and for the ones addressed to its role
turns them into spoken lines via the configured provider. Generation runs on a
**worker thread** with a bounded queue, so a slow (network) provider never blocks
the event bus or the match/vision pipelines — and old directives are dropped
rather than piling up, keeping commentary current.

If the provider fails (network, missing key), the generator falls back to the
offline mock so the broadcast keeps talking.
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from collections.abc import Callable

from ai_caster.commentary.lines import CommentaryLine, CommentaryLineGenerated
from ai_caster.commentary.prompts import system_prompt, user_prompt
from ai_caster.commentary.providers.base import LLMProvider, LLMRequest
from ai_caster.commentary.providers.mock import MockProvider
from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger
from ai_caster.director.directives import CommentaryDirective, CommentaryDirectiveIssued, Speaker

_log = get_logger("commentary.generator")

_SENTINEL = object()


class CommentaryGenerator:
    """Turns directives for one role into commentary lines."""

    def __init__(
        self,
        event_bus: EventBus,
        provider: LLMProvider,
        role: Speaker,
        *,
        model: str = "",
        language: str = "en",
        max_tokens: int = 90,
        queue_size: int = 16,
        enabled: bool = True,
        history: int = 100,
    ) -> None:
        self._bus = event_bus
        self._provider = provider
        self._fallback = MockProvider()
        self._role = role
        self._model = model
        self._language = language
        self._max_tokens = max_tokens
        self._enabled = enabled

        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._thread: threading.Thread | None = None
        self._recent: deque[CommentaryLine] = deque(maxlen=history)
        self._lock = threading.Lock()
        self._unsubscribe: Callable[[], None] | None = event_bus.subscribe(
            CommentaryDirectiveIssued, self._on_directive
        )

    # ------------------------------------------------------------------ #
    @property
    def role(self) -> Speaker:
        return self._role

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def recent_lines(self) -> list[CommentaryLine]:
        with self._lock:
            return list(self._recent)

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if self.is_running:
            return
        self._thread = threading.Thread(
            target=self._worker, name=f"commentary-{self._role.value}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            try:
                self._queue.put_nowait(_SENTINEL)
            except queue.Full:  # pragma: no cover - drain then signal
                with self._queue.mutex:
                    self._queue.queue.clear()
                self._queue.put_nowait(_SENTINEL)
            self._thread.join(timeout=3.0)
        self._thread = None

    def dispose(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self.stop()

    # ------------------------------------------------------------------ #
    def _on_directive(self, event: CommentaryDirectiveIssued) -> None:
        directive = event.directive
        if directive is None or directive.is_silence:
            return
        if directive.speaker.value != self._role.value:
            return
        if not self._enabled:
            return
        try:
            self._queue.put_nowait(directive)
        except queue.Full:
            # Drop the oldest pending directive to stay current.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(directive)
            except (queue.Empty, queue.Full):  # pragma: no cover - race
                pass

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                break
            try:
                line = self.generate(item)
            except Exception:  # noqa: BLE001 - keep the worker alive
                _log.exception("Commentary generation failed")
                continue
            if line.text:
                with self._lock:
                    self._recent.append(line)
                self._bus.publish(CommentaryLineGenerated(line=line))

    # ------------------------------------------------------------------ #
    def generate(self, directive: CommentaryDirective) -> CommentaryLine:
        """Produce a line for ``directive`` (synchronous; used by the worker/tests)."""
        request = LLMRequest(
            system=system_prompt(self._role.value, self._language),
            user=user_prompt(directive),
            topic=directive.topic,
            speaker=self._role.value,
            excitement=directive.excitement,
            context=directive.context,
            model=self._model,
            max_tokens=self._max_tokens,
        )
        provider_name = self._provider.name
        try:
            text = self._provider.generate(request)
        except Exception:  # noqa: BLE001 - keep the show going on provider failure
            _log.warning("Provider '%s' failed; using offline fallback.", self._provider.name)
            text = self._fallback.generate(request)
            provider_name = self._fallback.name
        return CommentaryLine(
            speaker=self._role.value,
            text=text.strip(),
            topic=directive.topic,
            excitement=directive.excitement,
            provider=provider_name,
            directive_kind=directive.kind.value,
            interrupt=directive.interrupt,
        )
