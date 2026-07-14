"""Licensing bus events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_caster.core.events import Event


@dataclass(frozen=True)
class LicenseStateChanged(Event):
    """The active license (and therefore the available entitlements) changed.

    ``status`` is a :class:`~ai_caster.licensing.models.LicenseStatus` value,
    ``tier`` the resolved tier name, and ``offline`` is ``True`` when the license
    was served from the offline cache rather than freshly validated.
    """

    status: str = "none"
    tier: str = "free"
    offline: bool = False
    entitlements: Any = None
    detail: str = ""
