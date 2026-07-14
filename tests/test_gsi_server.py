"""Tests for the FastAPI GSI transport, driven with Starlette's TestClient."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ai_caster.core.events import EventBus, GSIStateUpdated
from ai_caster.gsi.receiver import GSIReceiver
from ai_caster.gsi.server import create_gsi_app
from tests.conftest import make_gsi_payload


def _client(require_auth: bool = True) -> tuple[TestClient, list]:
    bus = EventBus()
    received = []
    bus.subscribe(GSIStateUpdated, received.append)
    receiver = GSIReceiver(bus, auth_token="secret", require_auth=require_auth)
    app = create_gsi_app(receiver)
    return TestClient(app), received


def test_post_valid_payload_returns_200_and_publishes():
    client, received = _client()
    resp = client.post("/", json=make_gsi_payload())
    assert resp.status_code == 200
    assert len(received) == 1
    assert received[0].game_state.map_name == "de_mirage"


def test_post_bad_token_returns_401():
    client, received = _client()
    resp = client.post("/", json=make_gsi_payload(token="nope"))
    assert resp.status_code == 401
    assert received == []


def test_post_non_json_returns_400():
    client, _ = _client()
    resp = client.post("/", content=b"not json", headers={"content-type": "application/json"})
    assert resp.status_code == 400


def test_post_non_object_json_returns_400():
    client, _ = _client()
    resp = client.post("/", json=[1, 2, 3])
    assert resp.status_code == 400


def test_health_endpoint_reports_counts():
    client, _ = _client()
    client.post("/", json=make_gsi_payload())
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["payloads"] == 1
    assert body["last_payload_at"] is not None
