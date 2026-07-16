"""Licensing backends.

The default :class:`OfflineLicensingBackend` issues a perpetual FREE-tier license
locally, so the product runs fully offline with no server. The
:class:`HttpLicensingBackend` validates against a real licensing service and lists
the account's registered devices. Both satisfy :class:`LicensingBackend`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from ai_caster.core.http import HttpError, delete_json, get_json, post_json
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


class SupabaseLicensingBackend:
    """Reads subscription tier and manages devices via Supabase (PostgREST).

    The tier comes from a ``profiles`` row and devices from a ``devices`` table
    (see ``docs/SUPABASE.md`` for the schema + RLS). Every request carries the
    anon key **and** the signed-in user's access token, so Row Level Security
    restricts each user to their own rows. No database password is ever used.
    """

    name = "supabase"

    def __init__(self, url: str, anon_key: str, *, device_name: str = "", timeout: float = 8.0):
        self._rest = url.rstrip("/") + "/rest/v1"
        self._anon = anon_key
        self._device_name = device_name
        self._timeout = timeout

    def _headers(self, token: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"apikey": self._anon, "Authorization": f"Bearer {token or self._anon}"}
        if extra:
            headers.update(extra)
        return headers

    def validate(self, account_id: str, device_id: str, *, token: str = "") -> License:
        try:
            rows = get_json(
                f"{self._rest}/profiles?id=eq.{account_id}&select=tier,tier_expires_at",
                headers=self._headers(token),
                timeout=self._timeout,
            )
        except HttpError as exc:
            raise LicensingError(str(exc)) from exc

        tier = SubscriptionTier.FREE
        expires_at: datetime | None = None
        if rows:
            try:
                tier = SubscriptionTier(str(rows[0].get("tier", "free")))
            except ValueError:
                tier = SubscriptionTier.FREE
            raw_expiry = rows[0].get("tier_expires_at")
            if raw_expiry:
                try:
                    expires_at = datetime.fromisoformat(str(raw_expiry).replace("Z", "+00:00"))
                except ValueError:
                    expires_at = None
        # A lapsed paid grant falls back to FREE (the License also carries the
        # expiry so the client can show it).
        if expires_at is not None and datetime.now(UTC) >= expires_at:
            tier = SubscriptionTier.FREE

        # Register / refresh this device (best effort; a failure never blocks use).
        try:
            post_json(
                f"{self._rest}/devices",
                {
                    "user_id": account_id,
                    "device_id": device_id,
                    "name": self._device_name or "This device",
                },
                headers=self._headers(token, {"Prefer": "resolution=merge-duplicates"}),
                timeout=self._timeout,
            )
        except HttpError as exc:  # pragma: no cover - best effort
            _log.debug("Device upsert skipped: %s", exc)

        return License(
            account_id=account_id, tier=tier, device_id=device_id, expires_at=expires_at
        )

    def list_devices(self, account_id: str, *, token: str = "") -> list[Device]:
        try:
            rows = get_json(
                f"{self._rest}/devices?user_id=eq.{account_id}&select=device_id,name,last_seen",
                headers=self._headers(token),
                timeout=self._timeout,
            )
        except HttpError as exc:
            _log.warning("Could not list devices: %s", exc)
            return []
        devices: list[Device] = []
        for entry in rows:
            last = entry.get("last_seen")
            last_seen = None
            if last:
                try:
                    last_seen = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                except ValueError:
                    last_seen = None
            devices.append(
                Device(
                    device_id=str(entry.get("device_id", "")),
                    name=str(entry.get("name", "")),
                    last_seen=last_seen,
                )
            )
        return devices

    def deregister_device(self, account_id: str, device_id: str, *, token: str = "") -> None:
        try:
            delete_json(
                f"{self._rest}/devices?user_id=eq.{account_id}&device_id=eq.{device_id}",
                headers=self._headers(token),
                timeout=self._timeout,
            )
        except HttpError as exc:  # best effort
            _log.warning("Could not deregister device: %s", exc)
