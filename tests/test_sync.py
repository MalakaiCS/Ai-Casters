"""Tests for cloud settings sync (gating, push, pull-and-apply)."""

from __future__ import annotations

from pathlib import Path

from ai_caster.auth.backend import OfflineAuthBackend
from ai_caster.auth.client import AuthClient
from ai_caster.config.manager import SettingsManager
from ai_caster.core.events import EventBus
from ai_caster.licensing.client import LicensingClient
from ai_caster.licensing.models import Device, License, SubscriptionTier
from ai_caster.sync.backend import NullSyncBackend
from ai_caster.sync.client import SettingsSyncClient
from ai_caster.sync.events import SettingsSynced

DEVICE = "device-sync"


class _TierBackend:
    """Licensing backend that issues a fixed tier."""

    name = "tier"

    def __init__(self, tier: SubscriptionTier) -> None:
        self._tier = tier

    def validate(self, account_id: str, device_id: str, *, token: str = "") -> License:
        return License(account_id=account_id, tier=self._tier, device_id=device_id)

    def list_devices(self, account_id: str, *, token: str = "") -> list[Device]:
        return []

    def deregister_device(self, account_id, device_id, *, token: str = "") -> None:
        return None


def _harness(tmp_path: Path, tier: SubscriptionTier, *, signed_in: bool, enabled: bool = True):
    bus = EventBus()
    settings = SettingsManager(tmp_path / "settings.json", bus)
    settings.load()

    auth = AuthClient(bus, OfflineAuthBackend(), device_id=DEVICE)
    if signed_in:
        auth.login("caster@example.com", "pw")

    licensing = LicensingClient(bus, _TierBackend(tier), device_id=DEVICE)
    licensing.validate("acc")

    backend = NullSyncBackend()
    sync = SettingsSyncClient(bus, backend, settings, auth, licensing, enabled=enabled)
    return bus, settings, sync, backend


def test_push_blocked_without_entitlement(tmp_path: Path):
    # FREE tier lacks CLOUD_SYNC.
    _, _, sync, backend = _harness(tmp_path, SubscriptionTier.FREE, signed_in=True)
    assert not sync.push()
    assert backend.pull("acc") is None


def test_push_blocked_when_signed_out(tmp_path: Path):
    _, _, sync, backend = _harness(tmp_path, SubscriptionTier.STUDIO, signed_in=False)
    assert not sync.push()


def test_push_blocked_when_disabled(tmp_path: Path):
    _, _, sync, _ = _harness(tmp_path, SubscriptionTier.STUDIO, signed_in=True, enabled=False)
    assert not sync.push()


def test_push_uploads_settings(tmp_path: Path):
    bus, settings, sync, backend = _harness(tmp_path, SubscriptionTier.STUDIO, signed_in=True)
    events: list[SettingsSynced] = []
    bus.subscribe(SettingsSynced, events.append)

    assert sync.push()
    account_id = "local-" + __import__("hashlib").sha256(b"caster@example.com").hexdigest()[:16]
    stored = backend.pull(account_id)
    assert stored is not None
    assert stored["gsi"]["port"] == settings.settings.gsi.port
    assert events[-1].direction == "push" and events[-1].ok


def test_pull_applies_remote_settings(tmp_path: Path):
    bus, settings, sync, backend = _harness(tmp_path, SubscriptionTier.STUDIO, signed_in=True)
    events: list[SettingsSynced] = []
    bus.subscribe(SettingsSynced, events.append)

    # Seed the remote store with a modified document.
    modified = settings.settings.model_copy(deep=True)
    modified.gsi.port = 4567
    account_id = sync._gate()[0]  # type: ignore[index]
    backend.push(account_id, modified.model_dump(mode="json"))

    assert sync.pull()  # returns True because local settings changed
    assert settings.settings.gsi.port == 4567
    assert events[-1].direction == "pull" and events[-1].changed


def test_pull_no_remote_is_noop(tmp_path: Path):
    _, settings, sync, _ = _harness(tmp_path, SubscriptionTier.STUDIO, signed_in=True)
    before = settings.settings.gsi.port
    assert not sync.pull()  # nothing stored -> no change
    assert settings.settings.gsi.port == before


def test_pull_rejects_invalid_remote_document(tmp_path: Path):
    bus, settings, sync, backend = _harness(tmp_path, SubscriptionTier.STUDIO, signed_in=True)
    events: list[SettingsSynced] = []
    bus.subscribe(SettingsSynced, events.append)
    account_id = sync._gate()[0]  # type: ignore[index]
    backend.push(account_id, {"gsi": {"port": "not-an-int-and-extra"}, "bogus": 1})

    assert not sync.pull()
    assert events[-1].direction == "pull" and not events[-1].ok
