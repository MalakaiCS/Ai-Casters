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


def make_player(
    steamid: str,
    name: str,
    team: str,
    *,
    health: int = 100,
    kills: int = 0,
    deaths: int = 0,
    assists: int = 0,
    mvps: int = 0,
    score: int = 0,
    round_kills: int = 0,
    round_killhs: int = 0,
    round_totaldmg: int = 0,
    money: int = 800,
    equip_value: int = 200,
) -> dict:
    """Build one ``allplayers`` entry with full state + match stats."""
    return {
        "_steamid": steamid,
        "name": name,
        "team": team,
        "state": {
            "health": health,
            "armor": 0,
            "money": money,
            "equip_value": equip_value,
            "round_kills": round_kills,
            "round_killhs": round_killhs,
            "round_totaldmg": round_totaldmg,
        },
        "match_stats": {
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "mvps": mvps,
            "score": score,
        },
    }


def make_state(
    players: list[dict],
    *,
    map_name: str = "de_mirage",
    map_phase: str = "live",
    round_no: int = 0,
    round_phase: str = "live",
    bomb: str | None = None,
    win_team: str | None = None,
    ct_score: int = 0,
    t_score: int = 0,
    ct_name: str = "Team A",
    t_name: str = "Team B",
    provider_ts: int | None = None,
    observed: str | None = None,
) -> dict:
    """Assemble a full spectator GSI payload dict from player descriptors."""
    allplayers = {p["_steamid"]: {k: v for k, v in p.items() if k != "_steamid"} for p in players}
    payload: dict = {
        "provider": {"name": "cs2", "appid": 730, "timestamp": provider_ts or 1000},
        "map": {
            "name": map_name,
            "phase": map_phase,
            "round": round_no,
            "team_ct": {"score": ct_score, "name": ct_name},
            "team_t": {"score": t_score, "name": t_name},
        },
        "round": {"phase": round_phase, "bomb": bomb, "win_team": win_team},
        "allplayers": allplayers,
    }
    if observed:
        payload["player"] = {"steamid": observed, "name": "observed"}
    return payload
