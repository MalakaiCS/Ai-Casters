"""Tests for rehearsal mode: recording, clip loading, scheduling and playback."""

from __future__ import annotations

import json

from ai_caster.core.events import EventBus, GSIStateUpdated
from ai_caster.gsi.receiver import GSIReceiver
from ai_caster.rehearsal.player import (
    RehearsalClip,
    RehearsalFrame,
    RehearsalPlayer,
    load_clip,
    schedule,
)
from ai_caster.rehearsal.recorder import GsiRecorder

from .conftest import make_gsi_payload


class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


# --- recorder -------------------------------------------------------------- #
def test_recorder_writes_relative_timestamps_and_strips_auth(tmp_path):
    clock = _FakeClock()
    rec = GsiRecorder(clock=clock)
    path = rec.start(tmp_path / "clip.jsonl")
    clock.t = 100.0
    rec.record({"auth": {"token": "secret"}, "map": {"name": "de_dust2"}})
    clock.t = 100.5
    rec.record(
        {"auth": {"token": "secret"}, "map": {"name": "de_dust2"}, "round": {"phase": "live"}}
    )
    assert rec.frame_count == 2
    rec.stop()

    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert [entry["t"] for entry in lines] == [0.0, 0.5]  # relative to first frame
    # Auth token is never persisted.
    assert all("auth" not in entry["payload"] for entry in lines)
    assert lines[0]["payload"]["map"]["name"] == "de_dust2"


def test_recorder_record_is_noop_when_not_recording(tmp_path):
    rec = GsiRecorder()
    rec.record({"map": {"name": "x"}})  # no open file -> silently ignored
    assert rec.frame_count == 0
    assert not rec.is_recording


# --- clip loading ---------------------------------------------------------- #
def test_load_clip_parses_and_skips_bad_lines(tmp_path):
    path = tmp_path / "c.jsonl"
    path.write_text(
        '{"t": 0.0, "payload": {"map": {"name": "a"}}}\n'
        "\n"  # blank line
        "not json at all\n"
        '{"t": 1.5, "payload": {"map": {"name": "b"}}}\n',
        encoding="utf-8",
    )
    clip = load_clip(path)
    assert len(clip) == 2
    assert clip.duration == 1.5
    assert clip.frames[0].payload["map"]["name"] == "a"


def test_load_clip_sorts_by_timestamp(tmp_path):
    path = tmp_path / "c.jsonl"
    path.write_text(
        '{"t": 2.0, "payload": {"n": 2}}\n{"t": 1.0, "payload": {"n": 1}}\n',
        encoding="utf-8",
    )
    clip = load_clip(path)
    assert [f.payload["n"] for f in clip.frames] == [1, 2]


# --- scheduling (pure) ----------------------------------------------------- #
def _clip(*times: float) -> RehearsalClip:
    return RehearsalClip(frames=tuple(RehearsalFrame(t, {"i": i}) for i, t in enumerate(times)))


def test_schedule_computes_inter_frame_delays():
    steps = schedule(_clip(0.0, 1.0, 3.0), speed=1.0)
    assert [d for d, _ in steps] == [0.0, 1.0, 2.0]


def test_schedule_scales_with_speed():
    steps = schedule(_clip(0.0, 2.0, 4.0), speed=2.0)
    assert [d for d, _ in steps] == [0.0, 1.0, 1.0]


def test_schedule_instant_when_speed_zero():
    steps = schedule(_clip(0.0, 1.0, 5.0), speed=0.0)
    assert [d for d, _ in steps] == [0.0, 0.0, 0.0]


# --- player ---------------------------------------------------------------- #
def test_player_feeds_every_payload_in_order():
    fed: list[dict] = []
    finished: list[bool] = []
    player = RehearsalPlayer(
        fed.append,
        on_finished=finished.append,
        sleep=lambda _d: False,  # never abort, no real sleeping
    )
    clip = _clip(0.0, 0.1, 0.2)
    player.play(clip, speed=1.0)
    player.stop()  # joins the worker
    assert [p["i"] for p in fed] == [0, 1, 2]
    assert player.progress == (3, 3)
    assert finished == [True]


def test_player_aborts_when_sleep_signals_stop():
    fed: list[dict] = []
    # Abort before the second frame's delay elapses.
    calls = {"n": 0}

    def fake_sleep(_delay: float) -> bool:
        calls["n"] += 1
        return calls["n"] >= 2  # stop on the second wait

    player = RehearsalPlayer(fed.append, sleep=fake_sleep)
    player.play(_clip(0.0, 1.0, 2.0), speed=1.0)
    player.stop()
    assert len(fed) == 1  # only the first frame made it through


# --- full loop: record via receiver -> load -> replay through receiver ------ #
def test_record_and_replay_round_trip_drives_the_pipeline(tmp_path):
    # 1. A live receiver records the payloads it authenticates.
    live_bus = EventBus()
    live = GSIReceiver(live_bus, auth_token="secret", require_auth=True)
    rec = GsiRecorder()
    live.set_recorder(rec.record)
    rec.start(tmp_path / "loop.jsonl")
    live.handle_payload(make_gsi_payload())
    live.handle_payload(make_gsi_payload())
    path = rec.stop()
    assert rec.frame_count == 2

    # 2. A fresh receiver replays the clip; the auth token is gone but replay
    #    bypasses auth, and every frame publishes a GSIStateUpdated downstream.
    replay_bus = EventBus()
    published: list = []
    replay_bus.subscribe(GSIStateUpdated, published.append)
    replay = GSIReceiver(replay_bus, auth_token="secret", require_auth=True)

    clip = load_clip(path)
    assert len(clip) == 2
    fed: list = []
    player = RehearsalPlayer(
        lambda payload: fed.append(replay.replay_payload(payload)),
        sleep=lambda _d: False,
    )
    player.play(clip, speed=0.0)  # instant
    player.stop()

    assert len(published) == 2  # the whole pipeline saw both replayed frames
    assert replay.payload_count == 2
