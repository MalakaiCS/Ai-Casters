"""Authentication bus events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_caster.core.events import Event


@dataclass(frozen=True)
class AuthStateChanged(Event):
    """The sign-in state changed.

    ``authenticated`` is the single fact subscribers care about; ``account`` is
    the :class:`~ai_caster.auth.models.Account` when signed in (``None`` when
    signed out), and ``detail`` carries a human-readable reason/error.
    """

    authenticated: bool = False
    account: Any = None
    detail: str = ""
