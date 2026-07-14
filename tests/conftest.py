"""Shared pytest fixtures.

Every test runs against an isolated application home directory so no test ever
reads or writes the real user's configuration or logs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_caster.core.paths import HOME_ENV_VAR, get_app_paths


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point all application directories at a per-test temp directory."""
    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path))
    return tmp_path


@pytest.fixture
def app_paths(isolated_home: Path):
    return get_app_paths().ensure()


def make_gsi_payload(token: str | None = "secret") -> dict:
    """A representative CS2 spectator GSI payload for tests."""
    payload: dict = {
        "provider": {"name": "Counter-Strike: Global Offensive", "appid": 730, "version": 14000},
        "map": {
            "name": "de_mirage",
            "phase": "live",
            "round": 4,
            "team_ct": {"score": 3, "name": "Team A"},
            "team_t": {"score": 2, "name": "Team B"},
        },
        "round": {"phase": "live", "bomb": "planted"},
        "player": {
            "steamid": "76561198000000000",
            "name": "s1mple_like_alias",
            "team": "CT",
            "state": {"health": 87, "armor": 100, "helmet": True, "money": 2400, "round_kills": 2},
            "match_stats": {"kills": 14, "assists": 3, "deaths": 9, "mvps": 2, "score": 31},
        },
        "allplayers": {
            "76561198000000001": {"name": "p1", "team": "CT", "state": {"health": 100}},
            "76561198000000002": {"name": "p2", "team": "T", "state": {"health": 0}},
            "76561198000000003": {"name": "p3", "team": "T", "state": {"health": 45}},
        },
    }
    if token is not None:
        payload["auth"] = {"token": token}
    return payload
