"""The licensing client (Module 4).

Validates the account's license through an injected backend, falling back to a
time-boxed offline cache when the service is unreachable, and exposes the
resolved :class:`Entitlements` so the rest of the app can gate features. Also
provides device management (list/deregister seats). Announces license state on
the event bus.
"""

from __future__ import annotations

import threading
from datetime import timedelta

from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger
from ai_caster.licensing.backend import LicensingBackend, LicensingError
from ai_caster.licensing.cache import LicenseCache
from ai_caster.licensing.events import LicenseStateChanged
from ai_caster.licensing.models import (
    Device,
    Entitlements,
    Feature,
    License,
    LicenseCheck,
    LicenseStatus,
    SubscriptionTier,
)
from ai_caster.licensing.tiers import entitlements_for

_log = get_logger("licensing.client")


class LicensingClient:
    """Resolves the active license + entitlements and manages devices."""

    def __init__(
        self,
        event_bus: EventBus,
        backend: LicensingBackend,
        *,
        device_id: str,
        cache: LicenseCache | None = None,
        offline_cache_days: int = 14,
    ) -> None:
        self._bus = event_bus
        self._backend = backend
        self._device_id = device_id
        self._cache = cache
        self._grace = timedelta(days=max(0, offline_cache_days))
        self._lock = threading.RLock()
        self._license: License | None = None
        self._status = LicenseStatus.NONE
        self._offline = False

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #
    @property
    def license(self) -> License | None:
        with self._lock:
            return self._license

    @property
    def status(self) -> LicenseStatus:
        with self._lock:
            return self._status

    @property
    def tier(self) -> SubscriptionTier:
        with self._lock:
            if self._license is None or self._status != LicenseStatus.ACTIVE:
                return SubscriptionTier.FREE
            return self._license.tier

    @property
    def entitlements(self) -> Entitlements:
        return entitlements_for(self.tier)

    def is_entitled(self, feature: Feature) -> bool:
        """Whether the active tier unlocks ``feature`` (the app's gate)."""
        return self.entitlements.allows(feature)

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def validate(self, account_id: str, *, token: str = "") -> LicenseCheck:
        """Validate online; on failure fall back to the offline cache.

        Publishes a :class:`LicenseStateChanged` reflecting the outcome.
        """
        try:
            license_ = self._backend.validate(account_id, self._device_id, token=token)
            if license_.is_expired():
                return self._apply(license_, LicenseStatus.EXPIRED, offline=False, detail="expired")
            if self._cache is not None:
                try:
                    self._cache.save(license_)
                except OSError:
                    _log.exception("Could not cache license")
            return self._apply(license_, LicenseStatus.ACTIVE, offline=False, detail="validated")
        except LicensingError as exc:
            _log.warning("Online validation failed (%s); trying offline cache.", exc)
            return self._from_cache(detail=str(exc))

    def _from_cache(self, *, detail: str) -> LicenseCheck:
        if self._cache is None:
            return self._apply(None, LicenseStatus.INVALID, offline=True, detail=detail)
        cached = self._cache.load(max_age=self._grace)
        if cached is None:
            return self._apply(None, LicenseStatus.INVALID, offline=True, detail="no valid cache")
        if cached.is_expired():
            return self._apply(cached, LicenseStatus.EXPIRED, offline=True, detail="cache expired")
        return self._apply(cached, LicenseStatus.ACTIVE, offline=True, detail="offline cache")

    def clear(self) -> None:
        """Drop the active license (e.g. on sign-out)."""
        if self._cache is not None:
            self._cache.clear()
        self._apply(None, LicenseStatus.NONE, offline=False, detail="cleared")

    # ------------------------------------------------------------------ #
    # Device management
    # ------------------------------------------------------------------ #
    def list_devices(self, account_id: str, *, token: str = "") -> list[Device]:
        """List the account's registered devices, flagging the current one."""
        devices = self._backend.list_devices(account_id, token=token)
        marked = [
            Device(
                device_id=d.device_id,
                name=d.name,
                last_seen=d.last_seen,
                current=d.device_id == self._device_id,
            )
            for d in devices
        ]
        if not any(d.current for d in marked):
            marked.append(Device(device_id=self._device_id, name="This device", current=True))
        return marked

    def deregister_device(self, account_id: str, device_id: str, *, token: str = "") -> None:
        self._backend.deregister_device(account_id, device_id, token=token)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _apply(
        self, license_: License | None, status: LicenseStatus, *, offline: bool, detail: str
    ) -> LicenseCheck:
        with self._lock:
            self._license = license_
            self._status = status
            self._offline = offline
        entitlements = entitlements_for(license_.tier if license_ else SubscriptionTier.FREE)
        self._bus.publish(
            LicenseStateChanged(
                status=str(status),
                tier=str(license_.tier) if license_ else str(SubscriptionTier.FREE),
                offline=offline,
                entitlements=entitlements,
                detail=detail,
            )
        )
        return LicenseCheck(license=license_, status=status, offline=offline, detail=detail)
