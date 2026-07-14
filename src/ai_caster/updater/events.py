"""Auto-updater bus events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_caster.core.events import Event


@dataclass(frozen=True)
class UpdateAvailable(Event):
    """A newer release than the running build is available.

    ``update`` is the :class:`~ai_caster.updater.models.UpdateInfo`; ``mandatory``
    is surfaced directly so subscribers can prompt more insistently.
    """

    update: Any = None
    current_version: str = ""
    latest_version: str = ""
    mandatory: bool = False
