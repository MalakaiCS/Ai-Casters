"""Tests for licensing: tiers/entitlements, cache, backend and client."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai_caster.core.events import EventBus
from ai_caster.licensing.backend import (
    LicensingBackend,
    LicensingError,
    OfflineLicensingBackend,
)
from ai_caster.licensing.cache import LicenseCache
from ai_caster.licensing.client import LicensingClient
from ai_caster.licensing.events import LicenseStateChanged
from ai_caster.licensing.models import (
    Device,
    Feature,
    License,
    LicenseStatus,
    SubscriptionTier,
)
from ai_caster.licensing.tiers import entitlements_for

DEVICE = "device-xyz"


# --- tiers / entitlements -------------------------------------------------- #
def test_tiers_are_nested_supersets():
    free = entitlements_for(SubscriptionTier.FREE)
    pro = entitlements_for(SubscriptionTier.PRO)
    studio = entitlements_for(SubscriptionTier.STUDIO)
    assert free.features <= pro.features <= studio.features
    assert free.allows(Feature.LIVE_CASTING)
    assert not free.allows(Feature.COMPUTER_VISION)
    assert pro.allows(Feature.OBS_INTEGRATION)
    assert studio.allows(Feature.CLOUD_SYNC)
    assert free.max_devices < studio.max_devices


# --- cache ----------------------------------------------------------------- #
def test_cache_roundtrip_within_grace(tmp_path: Path):
    cache = LicenseCache(tmp_path / "license.json")
    lic = License(account_id="acc", tier=SubscriptionTier.PRO, device_id=DEVICE)
    cache.save(lic)
    loaded = cache.load(max_age=timedelta(days=14))
    assert loaded is not None
    assert loaded.tier is SubscriptionTier.PRO
    assert loaded.account_id == "acc"


def test_cache_rejected_when_older_than_grace(tmp_path: Path):
    cache = LicenseCache(tmp_path / "license.json")
    cache.save(License(account_id="acc", tier=SubscriptionTier.PRO, device_id=DEVICE))
    future = datetime.now(UTC) + timedelta(days=30)
    assert cache.load(max_age=timedelta(days=14), now=future) is None


# --- backends -------------------------------------------------------------- #
def test_offline_backend_issues_free_license():
    lic = OfflineLicensingBackend().validate("acc", DEVICE)
    assert lic.tier is SubscriptionTier.FREE
    assert not lic.is_expired()


class _FailingBackend:
    name = "failing"

    def validate(self, account_id: str, device_id: str, *, token: str = "") -> License:
        raise LicensingError("service down")

    def list_devices(self, account_id: str, *, token: str = "") -> list[Device]:
        return []

    def deregister_device(self, account_id, device_id, *, token: str = "") -> None:
        return None


class _StubBackend:
    """Returns a configurable license and device list."""

    name = "stub"

    def __init__(self, license_: License, devices: list[Device] | None = None) -> None:
        self._license = license_
        self._devices = devices or []
        self.deregistered: list[str] = []

    def validate(self, account_id: str, device_id: str, *, token: str = "") -> License:
        return self._license

    def list_devices(self, account_id: str, *, token: str = "") -> list[Device]:
        return list(self._devices)

    def deregister_device(self, account_id, device_id, *, token: str = "") -> None:
        self.deregistered.append(device_id)


def _client(
    bus: EventBus, backend: LicensingBackend, cache: LicenseCache | None
) -> LicensingClient:
    return LicensingClient(bus, backend, device_id=DEVICE, cache=cache, offline_cache_days=14)


# --- client validation ----------------------------------------------------- #
def test_validate_online_active_and_caches(tmp_path: Path):
    bus = EventBus()
    events: list[LicenseStateChanged] = []
    bus.subscribe(LicenseStateChanged, events.append)
    lic = License(account_id="acc", tier=SubscriptionTier.PRO, device_id=DEVICE)
    cache = LicenseCache(tmp_path / "license.json")
    client = _client(bus, _StubBackend(lic), cache)

    check = client.validate("acc")
    assert check.status is LicenseStatus.ACTIVE
    assert client.tier is SubscriptionTier.PRO
    assert client.is_entitled(Feature.OBS_INTEGRATION)
    assert events[-1].tier == "pro"
    # It was written to the cache for offline use.
    assert cache.load(max_age=timedelta(days=14)) is not None


def test_validate_expired_downgrades_to_free(tmp_path: Path):
    bus = EventBus()
    expired = License(
        account_id="acc",
        tier=SubscriptionTier.PRO,
        device_id=DEVICE,
        expires_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    client = _client(bus, _StubBackend(expired), LicenseCache(tmp_path / "l.json"))
    check = client.validate("acc")
    assert check.status is LicenseStatus.EXPIRED
    assert client.tier is SubscriptionTier.FREE  # not ACTIVE, so FREE entitlements


def test_offline_fallback_uses_cache(tmp_path: Path):
    bus = EventBus()
    cache = LicenseCache(tmp_path / "license.json")
    cache.save(License(account_id="acc", tier=SubscriptionTier.STUDIO, device_id=DEVICE))
    client = _client(bus, _FailingBackend(), cache)

    check = client.validate("acc")
    assert check.offline
    assert check.status is LicenseStatus.ACTIVE
    assert client.tier is SubscriptionTier.STUDIO


def test_offline_fallback_without_cache_is_invalid(tmp_path: Path):
    bus = EventBus()
    client = _client(bus, _FailingBackend(), LicenseCache(tmp_path / "missing.json"))
    check = client.validate("acc")
    assert check.offline
    assert check.status is LicenseStatus.INVALID
    assert client.tier is SubscriptionTier.FREE


# --- device management ------------------------------------------------------ #
def test_list_devices_marks_current(tmp_path: Path):
    bus = EventBus()
    backend = _StubBackend(
        License(account_id="acc", tier=SubscriptionTier.PRO, device_id=DEVICE),
        devices=[Device(device_id="other", name="Laptop"), Device(device_id=DEVICE, name="Rig")],
    )
    client = _client(bus, backend, None)
    devices = client.list_devices("acc")
    current = [d for d in devices if d.current]
    assert len(current) == 1 and current[0].device_id == DEVICE


def test_list_devices_appends_current_when_absent(tmp_path: Path):
    bus = EventBus()
    backend = _StubBackend(
        License(account_id="acc", tier=SubscriptionTier.PRO, device_id=DEVICE),
        devices=[Device(device_id="other", name="Laptop")],
    )
    client = _client(bus, backend, None)
    devices = client.list_devices("acc")
    assert any(d.current and d.device_id == DEVICE for d in devices)


def test_deregister_device_delegates(tmp_path: Path):
    bus = EventBus()
    backend = _StubBackend(License(account_id="acc", tier=SubscriptionTier.PRO, device_id=DEVICE))
    client = _client(bus, backend, None)
    client.deregister_device("acc", "other")
    assert backend.deregistered == ["other"]


def test_clear_resets_to_none(tmp_path: Path):
    bus = EventBus()
    lic = License(account_id="acc", tier=SubscriptionTier.PRO, device_id=DEVICE)
    cache = LicenseCache(tmp_path / "license.json")
    client = _client(bus, _StubBackend(lic), cache)
    client.validate("acc")
    client.clear()
    assert client.status is LicenseStatus.NONE
    assert client.tier is SubscriptionTier.FREE
    assert cache.load(max_age=timedelta(days=14)) is None
