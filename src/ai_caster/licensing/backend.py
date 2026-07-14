"""Licensing backends.

The default :class:`OfflineLicensingBackend` issues a perpetual FREE-tier license
locally, so the product runs fully offline with no server. The
:class:`HttpLicensingBackend` validates against a real licensing service and lists
the account's registered devices. Both satisfy :class:`LicensingBackend`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from ai_caster.core.http import HttpError, get_json, post_json
from ai_caster.core.logging import get_logger
from ai_caster.licensing.models import Device, License, SubscriptionTier

_log = get_logger("licensing.backend")


@runtime_checkable
class LicensingBackend(Protocol):
    """Validates licenses and manages the account's devices."""

    @property
    def name(self) -> str: ...

    def validate(self, account_id: str, device_id: str, *, token: str = "") -> License: ...

    def list_devices(self, account_id: str, *, token: str = "") -> list[Device]: ...

    def deregister_device(self, account_id: str, device_id: str, *, token: str = "") -> None: ...


class LicensingError(RuntimeError):
    """A license could not be validated by the backend."""


class OfflineLicensingBackend:
    """Issues a local perpetual FREE license and knows only this device."""

    name = "offline"

    def __init__(self, *, tier: SubscriptionTier = SubscriptionTier.FREE) -> None:
        self._tier = tier

    def validate(self, account_id: str, device_id: str, *, token: str = "") -> License:
        return License(account_id=account_id or "offline", tier=self._tier, device_id=device_id)

    def list_devices(self, account_id: str, *, token: str = "") -> list[Device]:
        return []

    def deregister_device(self, account_id: str, device_id: str, *, token: str = "") -> None:
        return None


class HttpLicensingBackend:
    """Validates licenses against a real licensing service over JSON/HTTP."""

    name = "http"

    def __init__(self, base_url: str, *, timeout: float = 8.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _auth_header(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"} if token else {}

    def validate(self, account_id: str, device_id: str, *, token: str = "") -> License:
        try:  # pragma: no cover - needs a live server
            data = post_json(
                f"{self._base}/license/validate",
                {"account_id": account_id, "device_id": device_id},
                headers=self._auth_header(token),
                timeout=self._timeout,
            )
            expires = data.get("expires_at")
            return License(
                account_id=account_id,
                tier=SubscriptionTier(str(data.get("tier", "free"))),
                device_id=device_id,
                expires_at=datetime.fromisoformat(expires) if expires else None,
            )
        except (HttpError, ValueError) as exc:  # pragma: no cover - network/parse path
            raise LicensingError(str(exc)) from exc

    def list_devices(self, account_id: str, *, token: str = "") -> list[Device]:
        try:  # pragma: no cover - needs a live server
            data = get_json(
                f"{self._base}/license/devices?account_id={account_id}",
                headers=self._auth_header(token),
                timeout=self._timeout,
            )
            devices = []
            for entry in data.get("devices", []):
                last = entry.get("last_seen")
                devices.append(
                    Device(
                        device_id=str(entry.get("device_id", "")),
                        name=str(entry.get("name", "")),
                        last_seen=datetime.fromisoformat(last) if last else None,
                    )
                )
            return devices
        except (HttpError, ValueError) as exc:  # pragma: no cover - network/parse path
            _log.warning("Could not list devices: %s", exc)
            return []

    def deregister_device(self, account_id: str, device_id: str, *, token: str = "") -> None:
        try:  # pragma: no cover - needs a live server
            post_json(
                f"{self._base}/license/devices/remove",
                {"account_id": account_id, "device_id": device_id},
                headers=self._auth_header(token),
                timeout=self._timeout,
            )
        except HttpError as exc:  # pragma: no cover - best effort
            _log.warning("Could not deregister device: %s", exc)
