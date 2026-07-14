"""Persistence and lifecycle for :class:`~ai_caster.config.models.AppSettings`.

The :class:`SettingsManager` loads settings from a JSON file, validates them,
saves changes atomically, and notifies observers (and optionally the event bus)
when configuration changes. It is deliberately resilient: a missing or corrupt
file yields defaults plus a fresh saved copy rather than a crash — important for
an unattended broadcast tool.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from ai_caster.config.models import AppSettings
from ai_caster.core.events import EventBus, SettingsChanged
from ai_caster.core.logging import get_logger

_log = get_logger("config.manager")

SettingsObserver = Callable[[AppSettings], None]


class SettingsManager:
    """Owns the single :class:`AppSettings` instance and its persistence.

    Parameters
    ----------
    settings_file:
        Path to the JSON document. Its parent directory is created on save.
    event_bus:
        Optional bus; when provided a :class:`SettingsChanged` event is
        published on every successful save/reload so decoupled modules can react.
    """

    def __init__(self, settings_file: Path, event_bus: EventBus | None = None) -> None:
        self._path = Path(settings_file)
        self._bus = event_bus
        self._settings = AppSettings()
        self._observers: list[SettingsObserver] = []

    # ------------------------------------------------------------------ #
    # Accessors
    # ------------------------------------------------------------------ #
    @property
    def settings(self) -> AppSettings:
        """The current in-memory settings (always valid)."""
        return self._settings

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------ #
    # Load / save
    # ------------------------------------------------------------------ #
    def load(self) -> AppSettings:
        """Load settings from disk, validating and healing as needed.

        - Missing file -> defaults are used and written to disk.
        - Corrupt JSON or invalid schema -> the bad file is backed up, defaults
          are restored, and a warning is logged. The app keeps running.
        """
        if not self._path.exists():
            _log.info("No settings file at %s; writing defaults.", self._path)
            self._settings = AppSettings()
            self.save()
            self._notify("*")
            return self._settings

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._settings = AppSettings.model_validate(data)
            _log.info("Loaded settings from %s", self._path)
        except (json.JSONDecodeError, ValidationError, OSError) as exc:
            self._backup_corrupt_file()
            _log.warning("Settings at %s were invalid (%s); restored defaults.", self._path, exc)
            self._settings = AppSettings()
            self.save()

        self._notify("*")
        return self._settings

    def save(self) -> None:
        """Persist current settings atomically (write-temp-then-rename)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._settings.model_dump(mode="json")
        text = json.dumps(payload, indent=2, sort_keys=False)

        # Atomic write so a crash mid-save can't corrupt the live config.
        fd, tmp_name = tempfile.mkstemp(dir=self._path.parent, prefix=".settings-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp_name, self._path)
        except OSError:
            # Clean up the temp file on failure so we don't litter the dir.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        _log.debug("Saved settings to %s", self._path)

    def update(self, new_settings: AppSettings, *, section: str = "*") -> None:
        """Replace settings with a validated instance, persist and notify."""
        if not isinstance(new_settings, AppSettings):
            raise TypeError("update() requires an AppSettings instance")
        self._settings = new_settings
        self.save()
        self._notify(section)

    # ------------------------------------------------------------------ #
    # Observers
    # ------------------------------------------------------------------ #
    def add_observer(self, observer: SettingsObserver) -> Callable[[], None]:
        """Register a callback invoked with the settings on every change.

        Returns a callable that removes the observer.
        """
        self._observers.append(observer)
        return lambda: self._observers.remove(observer) if observer in self._observers else None

    def _notify(self, section: str) -> None:
        for observer in list(self._observers):
            try:
                observer(self._settings)
            except Exception:  # noqa: BLE001 - isolate observer failures
                _log.exception("Settings observer failed")
        if self._bus is not None:
            self._bus.publish(SettingsChanged(section=section))

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _backup_corrupt_file(self) -> None:
        backup = self._path.with_suffix(self._path.suffix + ".corrupt")
        try:
            self._path.replace(backup)
            _log.warning("Backed up corrupt settings to %s", backup)
        except OSError:
            _log.exception("Could not back up corrupt settings file")
