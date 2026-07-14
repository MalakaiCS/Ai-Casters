"""Module 19 — Auto Updater.

Checks the running build against a release manifest, announces newer versions on
the bus, and can download + checksum-verify an installer. The default backend
reports no updates (offline, no network); an HTTP backend reads a JSON manifest.
The updater surfaces updates rather than silently installing them.
"""

from ai_caster.updater.backend import HttpUpdateBackend, NullUpdateBackend, UpdateBackend
from ai_caster.updater.events import UpdateAvailable
from ai_caster.updater.models import UpdateCheck, UpdateInfo
from ai_caster.updater.updater import AutoUpdater
from ai_caster.updater.version import Version

__all__ = [
    "UpdateBackend",
    "NullUpdateBackend",
    "HttpUpdateBackend",
    "UpdateAvailable",
    "UpdateInfo",
    "UpdateCheck",
    "AutoUpdater",
    "Version",
]
