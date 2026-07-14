"""Tests for replay integration (models, receiver, HTTP transport)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_caster.core.events import EventBus
from ai_caster.replay.events import ReplayStateChanged
from ai_caster.replay.models import ReplayType
from ai_caster.replay.receiver import ReplayEventError, ReplayReceiver
from ai_caster.replay.server import create_replay_app


def _receiver() -> tuple[ReplayReceiver, list]:
    bus = EventBus()
    changes: list[ReplayStateChanged] = []
    bus.subscribe(ReplayStateChanged, changes.append)
    return ReplayReceiver(bus), changes


def test_started_sets_active_state_and_publishes():
    receiver, changes = _receiver()
    state = receiver.handle_event({"event": "started", "type": "clutch", "speed": 0.5})
    assert state.active is True
    assert state.replay_type is ReplayType.CLUTCH
    assert state.speed == 0.5
    assert state.is_slow_motion is True
    assert receiver.is_replay_active is True
    assert changes and changes[-1].transition == "started"


def test_ended_clears_state():
    receiver, _ = _receiver()
    receiver.handle_event({"event": "started"})
    state = receiver.handle_event({"event": "ended"})
    assert state.active is False
    assert receiver.is_replay_active is False


def test_speed_change_keeps_active():
    receiver, _ = _receiver()
    receiver.handle_event({"event": "started", "speed": 1.0})
    state = receiver.handle_event({"event": "speed", "speed": 0.25})
    assert state.active is True
    assert state.speed == 0.25


def test_unknown_type_falls_back_to_generic():
    receiver, _ = _receiver()
    state = receiver.handle_event({"event": "started", "type": "bogus"})
    assert state.replay_type is ReplayType.GENERIC


def test_unknown_event_raises():
    receiver, _ = _receiver()
    with pytest.raises(ReplayEventError):
        receiver.handle_event({"event": "explode"})


def test_invalid_speed_raises():
    receiver, _ = _receiver()
    with pytest.raises(ReplayEventError):
        receiver.handle_event({"event": "started", "speed": -1})


def test_http_transport_roundtrip():
    receiver, _ = _receiver()
    client = TestClient(create_replay_app(receiver))
    assert client.post("/", json={"event": "started", "type": "kill"}).status_code == 200
    assert receiver.is_replay_active is True
    assert client.get("/health").json()["replay_active"] is True
    assert client.post("/", json={"event": "ended"}).status_code == 200
    assert receiver.is_replay_active is False


def test_http_transport_rejects_bad_event():
    receiver, _ = _receiver()
    client = TestClient(create_replay_app(receiver))
    assert client.post("/", json={"event": "nope"}).status_code == 422
    assert client.post("/", json=[1, 2]).status_code == 400
