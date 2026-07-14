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
