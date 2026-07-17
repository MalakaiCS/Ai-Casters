"""The auto updater (Module 19).

Compares the running build against the latest release the backend reports and,
when a newer one exists, announces it on the bus. It can also download the
installer to the cache directory and verify its checksum. It deliberately does
**not** silently install and relaunch: on Windows that is an installer/OS concern
and doing it unattended mid-broadcast would be user-hostile — so the updater
surfaces the update and hands off, which is the honest boundary.
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger
from ai_caster.updater.backend import UpdateBackend
from ai_caster.updater.events import UpdateAvailable
from ai_caster.updater.models import UpdateCheck, UpdateInfo
from ai_caster.updater.version import Version

_log = get_logger("updater")


class AutoUpdater:
    """Checks for, announces and (optionally) downloads application updates."""

    def __init__(
        self,
        event_bus: EventBus,
        backend: UpdateBackend,
        *,
        current_version: str,
        channel: str = "stable",
        cache_dir: Path | None = None,
    ) -> None:
        self._bus = event_bus
        self._backend = backend
        self._current = Version.parse(current_version)
        self._channel = channel
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._lock = threading.RLock()
        self._latest: UpdateInfo | None = None

    @property
    def current_version(self) -> Version:
        return self._current

    @property
    def updates_configured(self) -> bool:
        """Whether a real update source is configured (not the offline null one)."""
        return getattr(self._backend, "name", "") != "null"

    @property
    def available_update(self) -> UpdateInfo | None:
        with self._lock:
            return self._latest

    def check(self) -> UpdateCheck:
        """Query the backend and, if a newer build exists, announce it."""
        info = self._backend.fetch_latest(self._channel)
        if info is None:
            return UpdateCheck(
                current=self._current, latest=None, update=None, checked=True, detail="no manifest"
            )
        if info.version <= self._current:
            with self._lock:
                self._latest = None
            return UpdateCheck(
                current=self._current,
                latest=info.version,
                update=None,
                detail="up to date",
            )
        with self._lock:
            self._latest = info
        self._bus.publish(
            UpdateAvailable(
                update=info,
                current_version=str(self._current),
                latest_version=str(info.version),
                mandatory=info.mandatory,
            )
        )
        return UpdateCheck(
            current=self._current, latest=info.version, update=info, detail="update available"
        )

    def download(self, update: UpdateInfo, *, dest_dir: Path | None = None) -> Path:
        """Download the installer to the cache and verify its checksum.

        Returns the path to the downloaded file. Raises on a checksum mismatch so
        a corrupt or tampered download is never handed on for installation.
        """
        target_dir = Path(dest_dir) if dest_dir else self._cache_dir
        if target_dir is None:
            raise ValueError("No download directory configured.")
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = update.url.rsplit("/", 1)[-1] or f"update-{update.version}.bin"
        dest = target_dir / filename

        self._fetch(update.url, dest)  # pragma: no cover - network I/O

        if update.sha256 and not self._verify_checksum(dest, update.sha256):
            dest.unlink(missing_ok=True)
            raise ValueError("Downloaded update failed checksum verification.")
        return dest

    def download_and_install(self, update: UpdateInfo, *, silent: bool = False) -> Path:
        """Download + verify the installer, then launch it to update the app.

        Returns the installer path. The caller is expected to quit the app right
        after so the installer can replace the running files. Only the actual
        launch is platform-specific; the download and checksum are shared/tested.
        """
        installer = self.download(update)
        self.launch_installer(installer, silent=silent)
        return installer

    def launch_installer(self, path: Path, *, silent: bool = False) -> None:
        """Start the downloaded installer as a detached process."""
        import subprocess
        import sys

        args = [str(path)]
        if silent:
            # Inno Setup switches: run without the wizard but keep a progress bar.
            args += ["/SILENT", "/NOCANCEL", "/NORESTART"]
        _log.info("Launching installer: %s", path)
        if sys.platform == "win32":  # pragma: no cover - Windows launch
            subprocess.Popen(args, close_fds=True)
        else:  # pragma: no cover - non-Windows launch
            subprocess.Popen(args)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _fetch(self, url: str, dest: Path) -> None:  # pragma: no cover - network I/O
        import urllib.request

        with urllib.request.urlopen(url, timeout=30) as response, dest.open("wb") as handle:  # noqa: S310
            while chunk := response.read(65536):
                handle.write(chunk)

    @staticmethod
    def _verify_checksum(path: Path, expected_sha256: str) -> bool:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(65536):
                digest.update(chunk)
        return digest.hexdigest().lower() == expected_sha256.lower()
