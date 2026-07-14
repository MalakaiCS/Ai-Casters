"""Tests for OBS integration (null controller + replay-driven scene switching)."""

from __future__ import annotations

from ai_caster.core.events import EventBus
from ai_caster.obs.controller import NullOBSController
from ai_caster.obs.integration import OBSIntegration
from ai_caster.replay.events import ReplayStateChanged
from ai_caster.replay.models import ReplayState, ReplayType


def _integration(bus: EventBus, **kwargs) -> tuple[OBSIntegration, NullOBSController]:
    controller = NullOBSController()
    integration = OBSIntegration(bus, controller, **kwargs)
    return integration, controller


def test_null_controller_records_scenes():
    controller = NullOBSController()
    assert not controller.is_connected
    controller.connect()
    assert controller.is_connected
    controller.set_scene("Live")
    controller.set_scene("Replay")
    assert controller.scenes_set == ["Live", "Replay"]
    assert controller.current_scene == "Replay"


def test_no_switch_when_auto_switch_disabled():
    bus = EventBus()
    integration, controller = _integration(bus, auto_switch_scenes=False)
    integration.connect()
    bus.publish(ReplayStateChanged(state=ReplayState(active=True), transition="started"))
    assert controller.scenes_set == []
    integration.dispose()


def test_no_switch_when_not_connected():
    bus = EventBus()
    integration, controller = _integration(bus, auto_switch_scenes=True)
    # Not connected: events must not drive scene changes.
    bus.publish(ReplayStateChanged(state=ReplayState(active=True), transition="started"))
    assert controller.scenes_set == []
    integration.dispose()


def test_switches_to_replay_scene_on_replay_start():
    bus = EventBus()
    integration, controller = _integration(
        bus, auto_switch_scenes=True, live_scene="LIVE", replay_scene="REPLAY"
    )
    integration.connect()
    state = ReplayState(active=True, replay_type=ReplayType.KILL)
    bus.publish(ReplayStateChanged(state=state, transition="started"))
    assert controller.current_scene == "REPLAY"
    integration.dispose()


def test_switches_back_to_live_scene_on_replay_end():
    bus = EventBus()
    integration, controller = _integration(
        bus, auto_switch_scenes=True, live_scene="LIVE", replay_scene="REPLAY"
    )
    integration.connect()
    bus.publish(ReplayStateChanged(state=ReplayState(active=True), transition="started"))
    bus.publish(ReplayStateChanged(state=ReplayState(active=False), transition="ended"))
    assert controller.scenes_set == ["REPLAY", "LIVE"]
    assert controller.current_scene == "LIVE"
    integration.dispose()


def test_dispose_unsubscribes_and_disconnects():
    bus = EventBus()
    integration, controller = _integration(bus, auto_switch_scenes=True)
    integration.connect()
    integration.dispose()
    assert not controller.is_connected
    # Further events are ignored after dispose.
    bus.publish(ReplayStateChanged(state=ReplayState(active=True), transition="started"))
    assert controller.scenes_set == []
