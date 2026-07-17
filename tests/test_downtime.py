"""Tests for downtime detection and the downtime commentator's decisions."""

from __future__ import annotations

from ai_caster.core.events import EventBus
from ai_caster.director.directives import CommentaryDirectiveIssued, Speaker
from ai_caster.downtime.commentator import DowntimeCommentator
from ai_caster.downtime.detect import detect_lull
from ai_caster.match.model import LiveMatch, Side, TeamModel


def _match(**kwargs) -> LiveMatch:
    base = dict(
        ct=TeamModel(Side.CT, "Vitality"),
        t=TeamModel(Side.T, "FaZe"),
    )
    base.update(kwargs)
    return LiveMatch(**base)


# --- detection ------------------------------------------------------------- #
def test_detect_timeout_side():
    assert detect_lull(_match(active_phase="timeout_ct")).timeout_side is Side.CT
    assert detect_lull(_match(active_phase="timeout_t")).timeout_side is Side.T
    assert detect_lull(_match(active_phase="timeout_ct")).kind == "timeout"


def test_detect_paused_and_breaks():
    assert detect_lull(_match(active_phase="paused")).kind == "paused"
    assert detect_lull(_match(match_phase="intermission")).kind == "halftime"
    assert detect_lull(_match(match_phase="warmup")).kind == "warmup"


def test_live_and_freezetime_are_not_lulls():
    assert not detect_lull(_match(active_phase="live")).active
    assert not detect_lull(_match(round_phase="freezetime")).active
    assert not detect_lull(None).active


# --- commentator decisions ------------------------------------------------- #
def _commentator(bus, **kwargs):
    # Slow-round filler off by default here so these tests isolate lull behaviour;
    # the dedicated slow-round tests below enable it explicitly.
    kwargs.setdefault("slow_round_enabled", False)
    return DowntimeCommentator(
        bus, min_delay_seconds=10.0, interval_seconds=20.0, clock=lambda: 0.0, **kwargs
    )


def test_waits_min_delay_then_speaks():
    dc = _commentator(EventBus())
    dc.on_model(_match(active_phase="timeout_ct"))  # lull starts at t=0
    assert dc.tick(5.0) is None  # too soon
    d = dc.tick(11.0)  # past the 10s delay
    assert d is not None
    assert d.speaker is Speaker.ANALYST  # analyst opens on a timeout
    assert d.topic == "timeout_expectation"
    assert d.context["team"] == "Vitality"  # the side that called it (CT)


def test_respects_interval_and_rotates_roles():
    dc = _commentator(EventBus())
    dc.on_model(_match(active_phase="timeout_ct"))
    first = dc.tick(11.0)
    assert dc.tick(20.0) is None  # within the 20s interval since last line
    second = dc.tick(40.0)
    assert first.speaker is Speaker.ANALYST
    assert second.speaker is Speaker.PLAY_BY_PLAY  # rotates to the play-by-play
    assert second.topic == "downtime_stat"


def test_silent_when_live():
    dc = _commentator(EventBus())
    dc.on_model(_match(active_phase="live"))
    assert dc.tick(100.0) is None


def test_silent_during_replay():
    dc = _commentator(EventBus())
    dc.on_model(_match(active_phase="timeout_ct"))
    dc.on_replay(True)
    assert dc.tick(100.0) is None
    dc.on_replay(False)
    assert dc.tick(100.0) is not None


def test_disabled_stays_quiet():
    dc = _commentator(EventBus(), enabled=False)
    dc.on_model(_match(active_phase="paused"))
    assert dc.tick(100.0) is None


def test_lull_ending_resets():
    dc = _commentator(EventBus())
    dc.on_model(_match(active_phase="timeout_ct"))
    dc.on_model(_match(active_phase="live"))  # lull ended
    assert dc.tick(100.0) is None


def test_directives_are_low_priority_non_interrupting():
    dc = _commentator(EventBus())
    dc.on_model(_match(active_phase="paused"))
    d = dc.tick(11.0)
    assert d.interrupt is False
    assert d.excitement < 0.4


def test_tick_publishes_nothing_when_no_lull_via_bus():
    bus = EventBus()
    issued: list = []
    bus.subscribe(CommentaryDirectiveIssued, issued.append)
    dc = _commentator(bus)  # slow-round filler off
    dc.on_model(_match(active_phase="live"))
    # Manually drive one decision the way the timer would.
    d = dc.tick(100.0)
    if d is not None:
        bus.publish(CommentaryDirectiveIssued(directive=d))
    assert issued == []


# --- slow / quiet live-round filler ---------------------------------------- #
from ai_caster.downtime.detect import is_live_round  # noqa: E402
from ai_caster.match.model import Momentum  # noqa: E402


class _MutClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _slow(bus, clock=None, **kwargs):
    kwargs.setdefault("slow_round_enabled", True)
    return DowntimeCommentator(
        bus,
        min_delay_seconds=10.0,
        interval_seconds=20.0,
        slow_round_after_seconds=16.0,
        slow_round_interval_seconds=18.0,
        round_intro_seconds=6.0,
        clock=clock or (lambda: 0.0),
        **kwargs,
    )


def test_is_live_round_only_true_during_live_play():
    assert is_live_round(_match(active_phase="live"))
    assert is_live_round(_match(round_phase="live"))
    assert not is_live_round(_match(round_phase="freezetime"))
    assert not is_live_round(_match(active_phase="timeout_ct"))
    assert not is_live_round(None)


def test_opening_map_control_line_fills_the_start_of_the_round():
    dc = _slow(EventBus())
    dc.on_model(_match(active_phase="live", map_name="de_inferno"))  # live starts at t=0
    assert dc.tick(3.0) is None  # before the opening delay (6s)
    d = dc.tick(8.0)  # opening map-control line
    assert d is not None
    assert d.topic == "map_control"
    assert d.reason == "quiet:map_control"
    assert d.interrupt is False
    assert d.excitement < 0.4
    assert d.context["map"] == "de_inferno"
    assert d.context["area"]  # a real callout area was chosen


def test_quiet_filler_resets_on_activity():
    clock = _MutClock()
    dc = _slow(EventBus(), clock=clock)
    dc.on_model(_match(active_phase="live"))  # live_since=0, intro armed
    # A real event lands at t=4 — the opening line must wait a fresh window from it.
    clock.t = 4.0
    dc._on_directive(CommentaryDirectiveIssued(directive=_live_directive()))
    assert dc.tick(8.0) is None  # only 4s since activity (< 6s intro)
    assert dc.tick(11.0) is not None  # 7s since activity -> opening line fires


def test_quiet_filler_ignores_its_own_output_as_activity():
    dc = _slow(EventBus())
    dc.on_model(_match(active_phase="live"))
    first = dc.tick(8.0)  # opening map-control line
    assert first is not None and first.reason == "quiet:map_control"
    # Feeding our own filler back must NOT count as match activity.
    dc._on_directive(CommentaryDirectiveIssued(directive=first))
    # A later quiet fill still comes on the slow cadence (not blocked by our own line).
    assert dc.tick(40.0) is not None


def test_quiet_filler_silent_when_disabled():
    dc = _slow(EventBus(), slow_round_enabled=False)
    dc.on_model(_match(active_phase="live"))
    assert dc.tick(100.0) is None


def test_quiet_filler_rotates_topics_after_the_opening():
    dc = _slow(EventBus())
    dc.on_model(_match(active_phase="live", map_name="de_inferno", momentum=Momentum(0.5)))
    opening = dc.tick(8.0)
    assert opening.topic == "map_control"
    # After the opening, the slow-cadence fills rotate through the mid-round topics.
    a = dc.tick(30.0)
    b = dc.tick(50.0)
    c = dc.tick(70.0)
    assert {a.topic, b.topic, c.topic} == {
        "slow_round_positioning",
        "slow_round_economy",
        "slow_round_stat",
    }


def _live_directive():
    from ai_caster.director.directives import (
        CommentaryDirective,
        DirectiveKind,
        DirectivePriority,
        Speaker,
    )

    return CommentaryDirective(
        speaker=Speaker.PLAY_BY_PLAY,
        kind=DirectiveKind.CALL,
        priority=DirectivePriority.HIGH,
        excitement=0.9,
        topic="Kill",
        reason="event:Kill",
    )
