"""Settings-sync bus events."""

from __future__ import annotations

from dataclasses import dataclass

from ai_caster.core.events import Event


@dataclass(frozen=True)
class SettingsSynced(Event):
    """A settings sync completed. ``direction`` is ``"push"`` or ``"pull"``;
    ``changed`` is ``True`` when a pull actually altered local settings."""

    direction: str = ""
    ok: bool = False
    changed: bool = False
    detail: str = ""
