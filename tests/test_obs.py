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


# --- scene reading + parsing helpers --------------------------------------- #
from ai_caster.config.models import OBSSettings  # noqa: E402
from ai_caster.obs.controller import (  # noqa: E402
    WebSocketOBSController,
    _scene_name,
    _scene_names,
)
from ai_caster.obs.factory import create_obs_controller  # noqa: E402


class _FakeResp:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _FakeReqClient:
    """Stands in for obsws_python.ReqClient in tests."""

    def __init__(self, scenes, current) -> None:
        self._scenes = scenes
        self._current = current

    def get_current_program_scene(self):
        return _FakeResp(current_program_scene_name=self._current)

    def get_scene_list(self):
        return _FakeResp(scenes=self._scenes, current_program_scene_name=self._current)

    def set_current_program_scene(self, scene):
        self._current = scene


def test_scene_name_reads_across_field_variants():
    assert _scene_name(_FakeResp(current_program_scene_name="Main")) == "Main"
    assert _scene_name(_FakeResp(scene_name="Alt")) == "Alt"
    assert _scene_name(_FakeResp(unrelated="x")) is None


def test_scene_names_parses_dicts_and_reverses_to_obs_order():
    # OBS returns newest-first; we present top-to-bottom.
    scenes = [{"sceneName": "Replay"}, {"sceneName": "Live"}, {"sceneName": "Intro"}]
    assert _scene_names(scenes) == ["Intro", "Live", "Replay"]
    assert _scene_names(None) == []


def test_websocket_controller_reads_scene_and_list_from_client():
    controller = WebSocketOBSController()
    controller._client = _FakeReqClient(
        scenes=[{"sceneName": "Replay"}, {"sceneName": "Live"}], current="Live"
    )
    assert controller.is_connected
    assert controller.get_current_scene() == "Live"
    assert controller.list_scenes() == ["Live", "Replay"]
    controller.set_scene("Replay")
    assert controller.current_scene == "Replay"


def test_websocket_controller_scene_ops_safe_when_disconnected():
    controller = WebSocketOBSController()
    assert controller.get_current_scene() is None
    assert controller.list_scenes() == []
    controller.set_scene("whatever")  # no client -> no-op, no raise


# --- factory --------------------------------------------------------------- #
def test_factory_returns_null_when_disabled():
    controller = create_obs_controller(OBSSettings(enabled=False))
    assert type(controller).__name__ == "NullOBSController"


def test_factory_returns_websocket_when_enabled_and_sdk_present(monkeypatch):
    import ai_caster.obs.factory as factory

    monkeypatch.setattr(factory, "obs_sdk_available", lambda: True)
    controller = factory.create_obs_controller(
        OBSSettings(enabled=True, host="10.0.0.5", port=4499, password="pw")
    )
    assert type(controller).__name__ == "WebSocketOBSController"
    assert controller._host == "10.0.0.5"
    assert controller._port == 4499


def test_factory_falls_back_to_null_without_sdk(monkeypatch):
    import ai_caster.obs.factory as factory

    monkeypatch.setattr(factory, "obs_sdk_available", lambda: False)
    controller = factory.create_obs_controller(OBSSettings(enabled=True))
    assert type(controller).__name__ == "NullOBSController"


# --- reconfigure ----------------------------------------------------------- #
def test_reconfigure_swaps_controller_and_disconnects_old():
    bus = EventBus()
    integration, old = _integration(bus, auto_switch_scenes=False)
    integration.connect()
    assert old.is_connected
    new = NullOBSController()
    integration.reconfigure(
        new, auto_switch_scenes=True, live_scene="L", replay_scene="R"
    )
    assert not old.is_connected  # old controller torn down
    assert integration.controller is new
    assert integration.auto_switch is True
    # New controller now drives scene switches with the new scene names.
    new.connect()
    bus.publish(ReplayStateChanged(state=ReplayState(active=True), transition="started"))
    assert new.current_scene == "R"
    integration.dispose()
