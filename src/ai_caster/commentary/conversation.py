"""Shared desk conversation — what makes two casters a *broadcast*.

Both commentary generators publish their lines on the bus but otherwise work in
isolation: each only ever saw its own recent output. This module keeps a single,
thread-safe, time-ordered record of what **both** casters have said, so each one
can see what its co-caster just put out and react to it ("—and like you said…")
instead of two announcers talking past each other.

It subscribes to :class:`CommentaryLineGenerated` and is read by the generators
when they build a prompt; it holds no opinions and generates no prose.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ai_caster.commentary.lines import CommentaryLineGenerated


@dataclass(frozen=True)
class ConversationTurn:
    """One spoken line on the desk, kept for cross-caster context."""

    speaker: str  # "play_by_play" | "analyst"
    text: str
    at: datetime


class ConversationMemory:
    """A rolling, shared transcript of the desk both generators can read."""

    def __init__(self, event_bus, *, history: int = 12) -> None:  # noqa: ANN001 - EventBus
        self._lock = threading.Lock()
        self._turns: deque[ConversationTurn] = deque(maxlen=history)
        self._unsubscribe: Callable[[], None] | None = event_bus.subscribe(
            CommentaryLineGenerated, self._on_line
        )

    # ------------------------------------------------------------------ #
    def _on_line(self, event: CommentaryLineGenerated) -> None:
        line = event.line
        if line is None or not line.text:
            return
        with self._lock:
            self._turns.append(ConversationTurn(line.speaker, line.text, line.created_at))

    # ------------------------------------------------------------------ #
    def record(self, speaker: str, text: str, at: datetime) -> None:
        """Record a turn directly (used in tests and non-bus contexts)."""
        if not text:
            return
        with self._lock:
            self._turns.append(ConversationTurn(speaker, text, at))

    def recent(self, count: int = 4) -> tuple[ConversationTurn, ...]:
        """The last ``count`` turns from either caster, oldest first."""
        with self._lock:
            turns = list(self._turns)
        return tuple(turns[-count:])

    def last_from_other(self, speaker: str) -> ConversationTurn | None:
        """The most recent line spoken by the *other* caster, if any."""
        with self._lock:
            for turn in reversed(self._turns):
                if turn.speaker != speaker:
                    return turn
        return None

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()

    def dispose(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
