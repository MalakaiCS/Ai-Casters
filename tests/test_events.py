"""Tests for the event bus."""

from __future__ import annotations

from ai_caster.core.events import Event, EventBus, GSIConnectionChanged, GSIStateUpdated


def test_subscribe_and_publish_delivers_event():
    bus = EventBus()
    received = []
    bus.subscribe(GSIStateUpdated, received.append)

    event = GSIStateUpdated(game_state={"map": "de_dust2"})
    bus.publish(event)

    assert received == [event]


def test_base_class_subscription_receives_all_events():
    bus = EventBus()
    received = []
    bus.subscribe(Event, received.append)

    bus.publish(GSIStateUpdated())
    bus.publish(GSIConnectionChanged(connected=True))

    assert len(received) == 2


def test_unsubscribe_stops_delivery():
    bus = EventBus()
    received = []
    unsubscribe = bus.subscribe(GSIStateUpdated, received.append)

    bus.publish(GSIStateUpdated())
    unsubscribe()
    bus.publish(GSIStateUpdated())

    assert len(received) == 1


def test_handler_exception_is_isolated():
    bus = EventBus()
    calls = []

    def bad(_event):
        raise RuntimeError("boom")

    bus.subscribe(GSIStateUpdated, bad)
    bus.subscribe(GSIStateUpdated, calls.append)

    # Should not raise despite the bad handler.
    bus.publish(GSIStateUpdated())
    assert len(calls) == 1


def test_event_has_utc_timestamp():
    event = GSIStateUpdated()
    assert event.timestamp.tzinfo is not None
