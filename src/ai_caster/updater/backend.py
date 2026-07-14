"""Update backends.

The default :class:`NullUpdateBackend` reports "no manifest", so the app never
claims a phantom update and needs no network. The :class:`HttpUpdateBackend`
fetches a JSON manifest describing the latest release for a channel. A backend
only *describes* the latest release; deciding whether it is newer than the running
build is the updater's job.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai_caster.core.http import HttpError, get_json
from ai_caster.core.logging import get_logger
from ai_caster.updater.models import UpdateInfo
from ai_caster.updater.version import Version

_log = get_logger("updater.backend")


@runtime_checkable
class UpdateBackend(Protocol):
    """Fetches the latest published release for a channel."""

    @property
    def name(self) -> str: ...

    def fetch_latest(self, channel: str) -> UpdateInfo | None: ...


class NullUpdateBackend:
    """Reports no updates (offline default)."""

    name = "null"

    def fetch_latest(self, channel: str) -> UpdateInfo | None:
        return None


class HttpUpdateBackend:
    """Reads a JSON release manifest over HTTP.

    Expected manifest shape::

        {"version": "0.2.0", "url": "https://.../setup.exe",
         "notes": "…", "mandatory": false, "sha256": "…"}
    """

    name = "http"

    def __init__(self, manifest_url: str, *, timeout: float = 8.0) -> None:
        self._url = manifest_url
        self._timeout = timeout

    def fetch_latest(self, channel: str) -> UpdateInfo | None:
        url = self._url.format(channel=channel) if "{channel}" in self._url else self._url
        try:  # pragma: no cover - needs a live server
            data = get_json(url, timeout=self._timeout)
            return UpdateInfo(
                version=Version.parse(str(data["version"])),
                url=str(data.get("url", "")),
                notes=str(data.get("notes", "")),
                mandatory=bool(data.get("mandatory", False)),
                sha256=str(data.get("sha256", "")),
            )
        except (HttpError, KeyError, ValueError) as exc:  # pragma: no cover - network/parse
            _log.warning("Update check failed: %s", exc)
            return None
