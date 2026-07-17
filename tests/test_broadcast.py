"""Tests for the broadcast controller (casting lifecycle, mute, forced replay)."""

from __future__ import annotations

from ai_caster.broadcast.controller import BroadcastController
from ai_caster.broadcast.events import BroadcastStateChanged
from ai_caster.core.events import EventBus
from ai_caster.replay.events import ReplayStateChanged


class _FakeCapture:
    def __init__(self) -> None:
        self.is_running = False
        self.starts = 0
        self.stops = 0

    def start(self) -> None:
        self.is_running = True
        self.starts += 1

    def stop(self) -> None:
        self.is_running = False
        self.stops += 1


class _FakeVision:
    def __init__(self) -> None:
        self.enabled = False

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


class _FakeVoice:
    def __init__(self) -> None:
        self.muted = False

    def set_muted(self, muted: bool) -> None:
        self.muted = muted


class _Licensing:
    def __init__(self, entitled: bool = True) -> None:
        self._entitled = entitled

    def is_entitled(self, feature) -> bool:
        return self._entitled


def _controller(bus: EventBus, *, entitled: bool = True):
    capture, vision, voice = _FakeCapture(), _FakeVision(), _FakeVoice()
    controller = BroadcastController(
        bus,
        capture=capture,
        vision=vision,
        voice=voice,
        licensing=_Licensing(entitled),
    )
    return controller, capture, vision, voice


def test_start_casting_starts_capture_and_vision():
    bus = EventBus()
    events: list[BroadcastStateChanged] = []
    bus.subscribe(BroadcastStateChanged, events.append)
    controller, capture, vision, _ = _controller(bus)

    assert controller.start_casting()
    assert controller.is_casting
    assert capture.is_running and vision.enabled
    assert events[-1].casting


def test_start_casting_blocked_without_entitlement():
    bus = EventBus()
    controller, capture, vision, _ = _controller(bus, entitled=False)
    assert not controller.start_casting()
    assert not controller.is_casting
    assert not capture.is_running and not vision.enabled


def test_stop_casting_stops_capture_and_vision():
    bus = EventBus()
    controller, capture, vision, _ = _controller(bus)
    controller.start_casting()
    controller.stop_casting()
    assert not controller.is_casting
    assert not capture.is_running and not vision.enabled


def test_toggle_casting_round_trips():
    bus = EventBus()
    controller, _, _, _ = _controller(bus)
    assert controller.toggle_casting() is True
    assert controller.toggle_casting() is False


def test_start_is_idempotent():
    bus = EventBus()
    controller, capture, _, _ = _controller(bus)
    controller.start_casting()
    controller.start_casting()
    assert capture.starts == 1


def test_mute_all_mutes_voice_and_publishes():
    bus = EventBus()
    events: list[BroadcastStateChanged] = []
    bus.subscribe(BroadcastStateChanged, events.append)
    controller, _, _, voice = _controller(bus)

    assert controller.toggle_mute() is True
    assert voice.muted and controller.is_muted
    assert events[-1].muted
    assert controller.toggle_mute() is False
    assert not voice.muted


def test_forced_replay_publishes_replay_state():
    bus = EventBus()
    replays: list[ReplayStateChanged] = []
    bus.subscribe(ReplayStateChanged, replays.append)
    controller, _, _, _ = _controller(bus)

    assert controller.toggle_forced_replay() is True
    assert replays[-1].state.active and replays[-1].transition == "started"
    assert controller.toggle_forced_replay() is False
    assert not replays[-1].state.active and replays[-1].transition == "ended"


def test_dispose_stops_casting():
    bus = EventBus()
    controller, capture, _, _ = _controller(bus)
    controller.start_casting()
    controller.dispose()
    assert not controller.is_casting and not capture.is_running
