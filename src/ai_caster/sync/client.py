"""Cloud settings sync.

Pushes the local settings document to, and pulls it from, a per-account cloud
store — so an operator's configuration follows them between machines. Syncing is
gated on the ``CLOUD_SYNC`` entitlement and on being signed in; when either is
absent it is a silent no-op (never an error mid-broadcast). Pulls are applied
through the settings manager, which validates the incoming document, so a bad
remote payload cannot corrupt the local config.
"""

from __future__ import annotations

from ai_caster.auth.client import AuthClient
from ai_caster.config.models import AppSettings
from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger
from ai_caster.licensing.client import LicensingClient
from ai_caster.licensing.models import Feature
from ai_caster.sync.backend import SyncBackend
from ai_caster.sync.events import SettingsSynced

_log = get_logger("sync.client")


class SettingsSyncClient:
    """Pushes/pulls the settings document for the signed-in account."""

    def __init__(
        self,
        event_bus: EventBus,
        backend: SyncBackend,
        settings_manager,
        auth: AuthClient,
        licensing: LicensingClient,
        *,
        enabled: bool = False,
    ) -> None:
        self._bus = event_bus
        self._backend = backend
        self._settings = settings_manager
        self._auth = auth
        self._licensing = licensing
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def _gate(self) -> tuple[str, str] | None:
        """Return (account_id, token) if syncing is allowed, else None."""
        if not self._enabled:
            return None
        if not self._licensing.is_entitled(Feature.CLOUD_SYNC):
            _log.debug("Cloud sync not entitled for the current tier.")
            return None
        session = self._auth.session
        if session is None:
            return None
        return session.account.user_id, session.access_token

    def push(self) -> bool:
        """Upload the current settings. Returns True if the push happened."""
        gate = self._gate()
        if gate is None:
            return False
        account_id, token = gate
        payload = self._settings.settings.model_dump(mode="json")
        try:
            self._backend.push(account_id, payload, token=token)
        except Exception as exc:  # noqa: BLE001 - sync must never disrupt the app
            _log.warning("Settings push failed: %s", exc)
            self._bus.publish(SettingsSynced(direction="push", ok=False, detail=str(exc)))
            return False
        self._bus.publish(SettingsSynced(direction="push", ok=True))
        return True

    def pull(self) -> bool:
        """Download and apply remote settings. Returns True if local settings
        changed as a result."""
        gate = self._gate()
        if gate is None:
            return False
        account_id, token = gate
        try:
            payload = self._backend.pull(account_id, token=token)
        except Exception as exc:  # noqa: BLE001 - sync must never disrupt the app
            _log.warning("Settings pull failed: %s", exc)
            self._bus.publish(SettingsSynced(direction="pull", ok=False, detail=str(exc)))
            return False
        if not payload:
            self._bus.publish(SettingsSynced(direction="pull", ok=True, changed=False))
            return False
        try:
            incoming = AppSettings.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 - reject invalid remote documents
            _log.warning("Remote settings were invalid: %s", exc)
            self._bus.publish(SettingsSynced(direction="pull", ok=False, detail=str(exc)))
            return False
        changed = incoming != self._settings.settings
        if changed:
            self._settings.update(incoming, section="*")
        self._bus.publish(SettingsSynced(direction="pull", ok=True, changed=changed))
        return changed
