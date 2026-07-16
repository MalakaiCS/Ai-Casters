"""The commentary provider interface.

A provider turns a prompt into a single line of text. The request carries both a
rendered ``system``/``user`` prompt (for API-backed models) **and** the
structured ``topic``/``context`` (for the template-based mock), so every backend
can be driven from the same call site and the mock stays fact-safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMRequest:
    """Everything a provider needs to produce one commentary line."""

    system: str
    user: str
    topic: str
    speaker: str
    excitement: float
    context: dict[str, Any] = field(default_factory=dict)
    # Recently spoken lines the model should avoid echoing, so the broadcast does
    # not repeat itself. Advisory: the mock ignores it (it rotates instead).
    avoid: tuple[str, ...] = ()
    # The recent back-and-forth on the desk as (speaker, text) pairs — including
    # the co-caster's lines — so this speaker can react to them (banter).
    conversation: tuple[tuple[str, str], ...] = ()
    model: str = ""  # blank -> provider default
    max_tokens: int = 90
    # Advisory only; providers that reject sampling params (e.g. Anthropic on
    # Opus 4.8) ignore it.
    temperature: float = 0.8


@runtime_checkable
class LLMProvider(Protocol):
    """Produces a single line of commentary text from a request."""

    @property
    def name(self) -> str: ...

    def generate(self, request: LLMRequest) -> str: ...
