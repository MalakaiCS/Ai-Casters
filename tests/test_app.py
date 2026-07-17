"""Tests for the composition root (headless, no UI)."""

from __future__ import annotations

from ai_caster.app import Application
from tests.conftest import make_gsi_payload


def test_application_wires_core(isolated_home):
    app = Application()
    # Settings loaded and a file written under the isolated home.
    assert app.paths.settings_file.exists()
    # GSI receiver uses the token from settings.
    token = app.settings.gsi.auth_token
    state = app.gsi_receiver.handle_payload(make_gsi_payload(token=token))
    assert state.map_name == "de_mirage"
    assert app.match_store.snapshot().map_name == "de_mirage"


def test_settings_change_reapplies_gsi_auth(isolated_home):
    app = Application()
    new = app.settings.model_copy(deep=True)
    new.gsi.auth_token = "rotated-token"
    app.settings_manager.update(new, section="gsi")

    # Old token now rejected, new token accepted.
    import pytest

    from ai_caster.gsi.receiver import GSIAuthError

    with pytest.raises(GSIAuthError):
        app.gsi_receiver.handle_payload(make_gsi_payload(token="stale"))
    app.gsi_receiver.handle_payload(make_gsi_payload(token="rotated-token"))


def test_application_wires_account_services(isolated_home):
    from ai_caster.licensing.models import SubscriptionTier

    app = Application()
    # A stable device id was created under config.
    assert app.device_id
    assert (app.paths.config_dir / "device.json").exists()

    # Offline defaults: sign in locally, validate the (free) license.
    assert app.auth.login("caster@example.com", "pw")
    account_id = app.auth.account.user_id
    check = app.licensing.validate(account_id)
    assert check.status.value == "active"
    assert app.licensing.tier is SubscriptionTier.FREE

    # No manifest configured -> updater reports up to date; sync is a no-op.
    assert not app.updater.check().available
    assert not app.sync.push()  # free tier lacks the cloud-sync entitlement


def test_application_broadcast_and_diagnostics(isolated_home):
    app = Application()
    # Broadcast control is wired to capture/vision and gated on the (free)
    # live-casting entitlement, which the default tier includes.
    assert app.broadcast.toggle_casting() is True
    assert app.capture.is_running and app.vision.enabled
    assert app.broadcast.toggle_casting() is False
    assert not app.capture.is_running and not app.vision.enabled

    # Master mute flows through to both voices.
    assert app.broadcast.toggle_mute() is True
    assert app.voice.play_by_play.dsp.muted and app.voice.analyst.dsp.muted
    app.broadcast.toggle_mute()

    # Hotkeys map to the broadcast actions (offline null backend by default).
    from ai_caster.hotkeys.actions import HotkeyAction

    app.hotkeys.trigger(HotkeyAction.TOGGLE_CASTING)
    assert app.broadcast.is_casting
    app.hotkeys.trigger(HotkeyAction.TOGGLE_CASTING)

    # Diagnostics produces a coherent snapshot on demand.
    snap = app.diagnostics.snapshot()
    assert snap.uptime_seconds >= 0.0
    app.broadcast.dispose()
    app.diagnostics.dispose()
