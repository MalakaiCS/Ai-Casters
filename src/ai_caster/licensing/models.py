"""Licensing models: subscription tiers, features, licenses and devices."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SubscriptionTier(StrEnum):
    """The subscription levels the product offers (no payment processing here)."""

    FREE = "free"
    PRO = "pro"
    STUDIO = "studio"


class Feature(StrEnum):
    """Individually gateable capabilities. Tiers map to sets of these."""

    LIVE_CASTING = "live_casting"
    COMPUTER_VISION = "computer_vision"
    OBS_INTEGRATION = "obs_integration"
    MULTI_LANGUAGE = "multi_language"
    CLOUD_SYNC = "cloud_sync"
    CUSTOM_VOICES = "custom_voices"


@dataclass(frozen=True)
class Entitlements:
    """What a tier unlocks: a feature set plus numeric limits."""

    tier: SubscriptionTier
    features: frozenset[Feature]
    max_devices: int
    max_voice_channels: int

    def allows(self, feature: Feature) -> bool:
        return feature in self.features


class LicenseStatus(StrEnum):
    """The current standing of the active license."""

    ACTIVE = "active"
    EXPIRED = "expired"
    INVALID = "invalid"
    NONE = "none"


@dataclass(frozen=True)
class Device:
    """A registered device (seat) under an account."""

    device_id: str
    name: str = ""
    last_seen: datetime | None = None
    current: bool = False


@dataclass(frozen=True)
class License:
    """An issued license for an account on a device.

    ``expires_at`` of ``None`` means perpetual (the offline FREE tier). ``status``
    is computed by the client against the current time and the offline grace
    window; the raw license simply carries the facts.
    """

    account_id: str
    tier: SubscriptionTier
    device_id: str
    issued_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime | None = None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or _utcnow()) >= self.expires_at


@dataclass(frozen=True)
class LicenseCheck:
    """The result of validating a license (online or from cache)."""

    license: License | None
    status: LicenseStatus
    offline: bool = False
    detail: str = ""
