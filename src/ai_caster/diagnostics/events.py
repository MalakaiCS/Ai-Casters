"""Diagnostics bus events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_caster.core.events import Event


@dataclass(frozen=True)
class DiagnosticsUpdated(Event):
    """A fresh :class:`~ai_caster.diagnostics.models.DiagnosticsSnapshot` is ready."""

    snapshot: Any = None
