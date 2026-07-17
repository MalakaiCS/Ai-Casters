"""Tests for the CS2 GSI config-file generator."""

from __future__ import annotations

from ai_caster.gsi.cfg import build_gsi_config, write_gsi_config


def test_build_config_contains_uri_and_token():
    text = build_gsi_config(host="127.0.0.1", port=3111, auth_token="tok123")
    assert "http://127.0.0.1:3111/" in text
    assert '"token"    "tok123"' in text
    # Requests key components used by the caster.
    assert '"allplayers_state"' in text
    assert '"player_weapons"' in text


def test_write_config_creates_file(tmp_path):
    path = write_gsi_config(tmp_path / "cfg", host="0.0.0.0", port=9000, auth_token="x")
    assert path.exists()
    assert path.name == "gamestate_integration_ai_caster.cfg"
    assert "http://0.0.0.0:9000/" in path.read_text(encoding="utf-8")
