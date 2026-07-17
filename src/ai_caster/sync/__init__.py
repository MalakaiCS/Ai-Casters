"""Cloud settings sync (part of Milestone 8).

Pushes/pulls the settings document to a per-account cloud store so configuration
follows the operator between machines. Gated on the ``CLOUD_SYNC`` entitlement and
sign-in; the default backend is a local no-op so the app runs offline. Pulled
documents are validated through the settings manager before they are applied.
"""

from ai_caster.sync.backend import (
    HttpSyncBackend,
    NullSyncBackend,
    SupabaseSyncBackend,
    SyncBackend,
)
from ai_caster.sync.client import SettingsSyncClient
from ai_caster.sync.events import SettingsSynced
from ai_caster.sync.factory import create_sync_backend

__all__ = [
    "SyncBackend",
    "NullSyncBackend",
    "HttpSyncBackend",
    "SupabaseSyncBackend",
    "create_sync_backend",
    "SettingsSyncClient",
    "SettingsSynced",
]
