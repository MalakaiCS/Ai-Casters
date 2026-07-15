"""Tests for the auto updater: version parsing, checks and checksums."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ai_caster.core.events import EventBus
from ai_caster.updater.backend import NullUpdateBackend, UpdateBackend
from ai_caster.updater.events import UpdateAvailable
from ai_caster.updater.models import UpdateInfo
from ai_caster.updater.updater import AutoUpdater
from ai_caster.updater.version import Version


# --- version --------------------------------------------------------------- #
def test_version_parsing_and_str():
    v = Version.parse("v1.2.3")
    assert (v.major, v.minor, v.patch) == (1, 2, 3)
    assert str(v) == "1.2.3"


def test_version_ordering():
    assert Version.parse("1.0.0") < Version.parse("1.0.1")
    assert Version.parse("1.2.0") < Version.parse("1.10.0")
    assert Version.parse("2.0.0") > Version.parse("1.9.9")


def test_prerelease_sorts_below_release():
    assert Version.parse("1.0.0-beta") < Version.parse("1.0.0")
    assert Version.parse("1.0.0-alpha") < Version.parse("1.0.0-beta")


def test_invalid_version_raises():
    with pytest.raises(ValueError):
        Version.parse("not-a-version")


# --- backends -------------------------------------------------------------- #
class _StubBackend:
    name = "stub"

    def __init__(self, info: UpdateInfo | None) -> None:
        self._info = info

    def fetch_latest(self, channel: str) -> UpdateInfo | None:
        return self._info


def _updater(bus: EventBus, backend: UpdateBackend, *, current="0.1.0", **kwargs) -> AutoUpdater:
    return AutoUpdater(bus, backend, current_version=current, **kwargs)


# --- check ----------------------------------------------------------------- #
def test_null_backend_reports_no_update():
    bus = EventBus()
    check = _updater(bus, NullUpdateBackend()).check()
    assert not check.available
    assert check.detail == "no manifest"


def test_updates_configured_reflects_backend():
    bus = EventBus()
    assert not _updater(bus, NullUpdateBackend()).updates_configured
    info = UpdateInfo(version=Version.parse("0.2.0"))
    assert _updater(bus, _StubBackend(info)).updates_configured


def test_check_reports_available_and_publishes():
    bus = EventBus()
    events: list[UpdateAvailable] = []
    bus.subscribe(UpdateAvailable, events.append)
    info = UpdateInfo(version=Version.parse("0.2.0"), url="http://x/setup.exe", mandatory=True)
    updater = _updater(bus, _StubBackend(info))

    check = updater.check()
    assert check.available
    assert updater.available_update is info
    assert events and events[-1].latest_version == "0.2.0"
    assert events[-1].mandatory


def test_check_up_to_date_does_not_publish():
    bus = EventBus()
    events: list[UpdateAvailable] = []
    bus.subscribe(UpdateAvailable, events.append)
    info = UpdateInfo(version=Version.parse("0.1.0"))
    check = _updater(bus, _StubBackend(info)).check()
    assert not check.available
    assert check.detail == "up to date"
    assert events == []


def test_older_latest_is_not_an_update():
    bus = EventBus()
    info = UpdateInfo(version=Version.parse("0.0.9"))
    check = _updater(bus, _StubBackend(info), current="0.1.0").check()
    assert not check.available


# --- checksum -------------------------------------------------------------- #
def test_checksum_verification(tmp_path: Path):
    payload = b"installer-bytes"
    path = tmp_path / "setup.bin"
    path.write_bytes(payload)
    good = hashlib.sha256(payload).hexdigest()
    assert AutoUpdater._verify_checksum(path, good)
    assert not AutoUpdater._verify_checksum(path, "deadbeef")


def test_download_requires_a_directory():
    bus = EventBus()
    updater = _updater(bus, NullUpdateBackend())  # no cache_dir configured
    with pytest.raises(ValueError):
        updater.download(UpdateInfo(version=Version.parse("0.2.0"), url="http://x/a.bin"))


def test_download_and_install_requires_a_directory():
    bus = EventBus()
    updater = _updater(bus, NullUpdateBackend())  # no cache_dir -> download() raises
    with pytest.raises(ValueError):
        updater.download_and_install(UpdateInfo(version=Version.parse("0.2.0"), url="http://x/a.bin"))
