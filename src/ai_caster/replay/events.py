"""Replay bus events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_caster.core.events import Event


@dataclass(frozen=True)
class ReplayStateChanged(Event):
    """The replay state changed (started, ended or speed changed).

    ``state`` is an immutable :class:`~ai_caster.replay.models.ReplayState`
    (typed ``Any`` to avoid import cycles in :mod:`core`-adjacent code).
    ``transition`` names what happened: ``"started"``, ``"ended"`` or ``"speed"``.
    """

    state: Any = None
    transition: str = ""
