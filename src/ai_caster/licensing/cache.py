"""Offline license cache.

When the licensing service is unreachable the app must keep working for a bounded
grace period rather than locking the operator out mid-broadcast. This stores the
last successfully validated license as JSON with the time it was cached; the
client accepts it while it is within both the license's own expiry and the
configured offline grace window.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai_caster.core.logging import get_logger
from ai_caster.licensing.models import License, SubscriptionTier

_log = get_logger("licensing.cache")


class LicenseCache:
    """Persists and reloads the last-known-good license with a cache timestamp."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def save(self, license_: License) -> None:
        payload = {
            "cached_at": datetime.now(UTC).isoformat(),
            "account_id": license_.account_id,
            "tier": str(license_.tier),
            "device_id": license_.device_id,
            "issued_at": license_.issued_at.isoformat(),
            "expires_at": license_.expires_at.isoformat() if license_.expires_at else None,
        }
        text = json.dumps(payload, indent=2)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".license-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, self._path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def load(self, *, max_age: timedelta, now: datetime | None = None) -> License | None:
        """Return the cached license if present and cached within ``max_age``."""
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(data["cached_at"])
            if (now or datetime.now(UTC)) - cached_at > max_age:
                _log.info("Cached license is older than the offline grace window.")
                return None
            expires = data.get("expires_at")
            return License(
                account_id=str(data["account_id"]),
                tier=SubscriptionTier(str(data["tier"])),
                device_id=str(data["device_id"]),
                issued_at=datetime.fromisoformat(data["issued_at"]),
                expires_at=datetime.fromisoformat(expires) if expires else None,
            )
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
            _log.warning("Ignoring unreadable license cache (%s).", exc)
            return None

    def clear(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            _log.exception("Could not clear license cache")
