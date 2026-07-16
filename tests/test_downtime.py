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
    dc = _commentator(bus)
    dc.on_model(_match(active_phase="live"))
    # Manually drive one decision the way the timer would.
    d = dc.tick(100.0)
    if d is not None:
        bus.publish(CommentaryDirectiveIssued(directive=d))
    assert issued == []
