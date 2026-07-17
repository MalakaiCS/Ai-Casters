"""Auto-updater models."""

from __future__ import annotations

from dataclasses import dataclass

from ai_caster.updater.version import Version


@dataclass(frozen=True)
class UpdateInfo:
    """A published release, as described by the update manifest."""

    version: Version
    url: str = ""
    notes: str = ""
    mandatory: bool = False
    sha256: str = ""


@dataclass(frozen=True)
class UpdateCheck:
    """The result of checking for updates."""

    current: Version
    latest: Version | None
    update: UpdateInfo | None  # populated only when an update is available
    checked: bool = True
    detail: str = ""

    @property
    def available(self) -> bool:
        return self.update is not None
