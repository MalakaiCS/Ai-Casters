"""Tests for the framework-agnostic GSI receiver."""

from __future__ import annotations

from datetime import timedelta

import pytest

from ai_caster.core.events import EventBus, GSIConnectionChanged, GSIStateUpdated
from ai_caster.gsi.receiver import GSIAuthError, GSIReceiver
from tests.conftest import make_gsi_payload


def _make_receiver(**kwargs) -> tuple[GSIReceiver, list, list]:
    bus = EventBus()
    states, conns = [], []
    bus.subscribe(GSIStateUpdated, states.append)
    bus.subscribe(GSIConnectionChanged, conns.append)
    receiver = GSIReceiver(bus, auth_token="secret", **kwargs)
    return receiver, states, conns


def test_handle_payload_parses_and_publishes():
    receiver, states, conns = _make_receiver()
    state = receiver.handle_payload(make_gsi_payload())

    assert state.map_name == "de_mirage"
    assert len(states) == 1
    assert states[0].game_state is state
    # First payload flips connection to connected.
    assert conns and conns[0].connected is True
    assert receiver.payload_count == 1
    assert receiver.match_store.snapshot().map_name == "de_mirage"


def test_bad_token_rejected():
    receiver, states, _ = _make_receiver()
    with pytest.raises(GSIAuthError):
        receiver.handle_payload(make_gsi_payload(token="wrong"))
    assert states == []


def test_missing_token_rejected_when_required():
    receiver, _, _ = _make_receiver()
    with pytest.raises(GSIAuthError):
        receiver.handle_payload(make_gsi_payload(token=None))


def test_auth_disabled_allows_any_payload():
    bus = EventBus()
    receiver = GSIReceiver(bus, auth_token="secret", require_auth=False)
    state = receiver.handle_payload(make_gsi_payload(token=None))
    assert state.map_name == "de_mirage"


def test_update_auth_applies_new_token():
    receiver, _, _ = _make_receiver()
    receiver.update_auth("newtoken", True)
    with pytest.raises(GSIAuthError):
        receiver.handle_payload(make_gsi_payload(token="secret"))
    receiver.handle_payload(make_gsi_payload(token="newtoken"))  # ok now


def test_connection_event_emitted_once_until_disconnect():
    receiver, _, conns = _make_receiver()
    receiver.handle_payload(make_gsi_payload())
    receiver.handle_payload(make_gsi_payload())
    # Only one connect event despite two payloads.
    assert sum(1 for c in conns if c.connected) == 1

    receiver.mark_disconnected()
    assert conns[-1].connected is False


def test_staleness_detection():
    receiver, _, _ = _make_receiver()
    receiver.handle_payload(make_gsi_payload())
    last = receiver.last_payload_at
    assert receiver.is_stale(5.0, now=last) is False
    assert receiver.is_stale(5.0, now=last + timedelta(seconds=6)) is True
