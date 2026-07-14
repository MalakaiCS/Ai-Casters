"""Module 4 — Licensing Client.

License validation with subscription tiers, feature entitlements, device
management and a time-boxed offline cache. The default backend issues a local
perpetual FREE license so the product runs offline; an HTTP backend validates
against a real service. No payment processing lives here — only validation and
entitlement resolution.
"""

from ai_caster.licensing.backend import (
    HttpLicensingBackend,
    LicensingBackend,
    LicensingError,
    OfflineLicensingBackend,
)
from ai_caster.licensing.cache import LicenseCache
from ai_caster.licensing.client import LicensingClient
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
from ai_caster.licensing.tiers import ENTITLEMENTS, entitlements_for

__all__ = [
    "LicensingBackend",
    "OfflineLicensingBackend",
    "HttpLicensingBackend",
    "LicensingError",
    "LicenseCache",
    "LicensingClient",
    "LicenseStateChanged",
    "Device",
    "Entitlements",
    "Feature",
    "License",
    "LicenseCheck",
    "LicenseStatus",
    "SubscriptionTier",
    "ENTITLEMENTS",
    "entitlements_for",
]
