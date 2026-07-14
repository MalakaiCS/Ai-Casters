"""Tests for the settings models and SettingsManager."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from ai_caster.config.manager import SettingsManager
from ai_caster.config.models import AppSettings, LoggingSettings
from ai_caster.core.events import EventBus, SettingsChanged


def test_defaults_are_valid():
    settings = AppSettings()
    assert settings.gsi.port == 3111
    assert settings.gsi.auth_token  # auto-generated, non-empty
    assert settings.commentary.language.value == "en"
    assert settings.voice.play_by_play.volume == 1.0


def test_generated_tokens_are_unique():
    assert AppSettings().gsi.auth_token != AppSettings().gsi.auth_token


def test_invalid_port_rejected():
    with pytest.raises(ValidationError):
        AppSettings(gsi={"port": 70000})


def test_logging_level_validation():
    assert LoggingSettings(level="debug").level == "DEBUG"
    with pytest.raises(ValidationError):
        LoggingSettings(level="verbose")


def test_extra_keys_forbidden():
    with pytest.raises(ValidationError):
        AppSettings(unknown_section={})


def test_manager_creates_defaults_when_missing(app_paths):
    manager = SettingsManager(app_paths.settings_file)
    assert not app_paths.settings_file.exists()
    manager.load()
    assert app_paths.settings_file.exists()
    assert manager.settings.gsi.port == 3111


def test_manager_round_trips(app_paths):
    manager = SettingsManager(app_paths.settings_file)
    manager.load()
    new = manager.settings.model_copy(deep=True)
    new.gsi.port = 4000
    manager.update(new)

    reloaded = SettingsManager(app_paths.settings_file)
    reloaded.load()
    assert reloaded.settings.gsi.port == 4000


def test_manager_heals_corrupt_file(app_paths):
    app_paths.settings_file.write_text("{ this is not json", encoding="utf-8")
    manager = SettingsManager(app_paths.settings_file)
    manager.load()
    # Defaults restored, corrupt file backed up.
    assert manager.settings.gsi.port == 3111
    assert app_paths.settings_file.with_suffix(".json.corrupt").exists()
    # And a fresh valid file was written.
    json.loads(app_paths.settings_file.read_text(encoding="utf-8"))


def test_manager_atomic_save_leaves_no_temp_files(app_paths):
    manager = SettingsManager(app_paths.settings_file)
    manager.load()
    manager.save()
    leftovers = list(app_paths.config_dir.glob(".settings-*.tmp"))
    assert leftovers == []


def test_manager_publishes_settings_changed(app_paths):
    bus = EventBus()
    events = []
    bus.subscribe(SettingsChanged, events.append)
    manager = SettingsManager(app_paths.settings_file, bus)
    manager.load()  # publishes one "*"
    manager.update(manager.settings.model_copy(deep=True), section="gsi")
    sections = [e.section for e in events]
    assert "*" in sections and "gsi" in sections


def test_observer_invoked_on_change(app_paths):
    manager = SettingsManager(app_paths.settings_file)
    seen = []
    manager.add_observer(lambda s: seen.append(s.gsi.port))
    manager.load()
    assert seen and seen[-1] == 3111
