"""The tier → entitlements mapping.

One table, so feature gating everywhere else is a lookup rather than scattered
``if tier == ...`` checks. Higher tiers are supersets of lower ones.
"""

from __future__ import annotations

from ai_caster.licensing.models import Entitlements, Feature, SubscriptionTier

_FREE_FEATURES = frozenset({Feature.LIVE_CASTING})
_PRO_FEATURES = _FREE_FEATURES | {
    Feature.COMPUTER_VISION,
    Feature.OBS_INTEGRATION,
    Feature.MULTI_LANGUAGE,
}
_STUDIO_FEATURES = _PRO_FEATURES | {Feature.CLOUD_SYNC, Feature.CUSTOM_VOICES}

ENTITLEMENTS: dict[SubscriptionTier, Entitlements] = {
    SubscriptionTier.FREE: Entitlements(
        tier=SubscriptionTier.FREE,
        features=_FREE_FEATURES,
        max_devices=1,
        max_voice_channels=2,
    ),
    SubscriptionTier.PRO: Entitlements(
        tier=SubscriptionTier.PRO,
        features=_PRO_FEATURES,
        max_devices=3,
        max_voice_channels=2,
    ),
    SubscriptionTier.STUDIO: Entitlements(
        tier=SubscriptionTier.STUDIO,
        features=_STUDIO_FEATURES,
        max_devices=10,
        max_voice_channels=2,
    ),
}


def entitlements_for(tier: SubscriptionTier) -> Entitlements:
    """Return the entitlements for ``tier`` (FREE if somehow unknown)."""
    return ENTITLEMENTS.get(tier, ENTITLEMENTS[SubscriptionTier.FREE])
