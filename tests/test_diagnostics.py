"""Tests for diagnostics: collector, resource sampling, engine and log tail."""

from __future__ import annotations

import time
from pathlib import Path

from ai_caster.capture.timing import CaptureStats
from ai_caster.core.events import Event, EventBus, SettingsChanged
from ai_caster.diagnostics.collector import DiagnosticsCollector, DiagnosticsSources
from ai_caster.diagnostics.engine import DiagnosticsEngine
from ai_caster.diagnostics.events import DiagnosticsUpdated
from ai_caster.diagnostics.logs import tail_log
from ai_caster.diagnostics.models import DiagnosticsSnapshot


# --- model ----------------------------------------------------------------- #
def test_snapshot_defaults_and_uptime_clock():
    snap = DiagnosticsSnapshot(uptime_seconds=3661)
    assert snap.uptime_clock == "1:01:01"
    assert snap.cpu_percent is None  # honest about missing data
    assert snap.timestamp is not None


# --- collector ------------------------------------------------------------- #
def test_collector_reads_sources():
    stats = CaptureStats(source="synthetic", running=True, actual_fps=59.5, frames_captured=100)
    sources = DiagnosticsSources(
        gsi_connected=lambda: True,
        capture_stats=lambda: stats,
        vision_enabled=lambda: True,
        vision_processed=lambda: 42,
        voice_pending=lambda: (2, 1),
        replay_active=lambda: True,
        casting=lambda: True,
        muted=lambda: False,
    )
    collector = DiagnosticsCollector(sources=sources, resource_sampler=lambda: (12.5, 256.0))
    snap = collector.snapshot(uptime_seconds=10.0, event_count=7)

    assert snap.gsi_connected and snap.casting and snap.replay_active
    assert snap.capture_running and snap.capture_fps == 59.5
    assert snap.vision_enabled and snap.vision_processed == 42
    assert snap.voice_pending_play_by_play == 2 and snap.voice_pending_analyst == 1
    assert snap.cpu_percent == 12.5 and snap.memory_mb == 256.0
    assert snap.event_count == 7


def test_collector_handles_missing_capture_stats():
    collector = DiagnosticsCollector(
        sources=DiagnosticsSources(), resource_sampler=lambda: (None, None)
    )
    snap = collector.snapshot(uptime_seconds=1.0, event_count=0)
    assert not snap.capture_running
    assert snap.capture_fps == 0.0
    assert snap.cpu_percent is None


# --- engine ---------------------------------------------------------------- #
def test_engine_counts_events_excluding_own():
    bus = EventBus()
    engine = DiagnosticsEngine(
        bus, DiagnosticsCollector(resource_sampler=lambda: (None, None)), poll_interval=0.25
    )
    try:
        bus.publish(SettingsChanged(section="gsi"))
        bus.publish(SettingsChanged(section="voice"))
        # Its own DiagnosticsUpdated must not be counted.
        bus.publish(DiagnosticsUpdated(snapshot=None))
        assert engine.event_count == 2
    finally:
        engine.dispose()


def test_engine_snapshot_on_demand():
    bus = EventBus()
    engine = DiagnosticsEngine(bus, DiagnosticsCollector(resource_sampler=lambda: (None, None)))
    try:
        snap = engine.snapshot()
        assert isinstance(snap, DiagnosticsSnapshot)
        assert snap.uptime_seconds >= 0.0
    finally:
        engine.dispose()


def test_engine_publishes_on_timer():
    bus = EventBus()
    published: list[DiagnosticsUpdated] = []
    bus.subscribe(DiagnosticsUpdated, published.append)
    engine = DiagnosticsEngine(
        bus, DiagnosticsCollector(resource_sampler=lambda: (None, None)), poll_interval=0.25
    )
    engine.start()
    try:
        deadline = time.monotonic() + 2.0
        while not published and time.monotonic() < deadline:
            time.sleep(0.02)
        assert published, "diagnostics engine did not publish a snapshot"
        assert isinstance(published[0].snapshot, DiagnosticsSnapshot)
    finally:
        engine.dispose()
    assert not engine.is_running


def test_engine_dispose_unsubscribes():
    bus = EventBus()
    engine = DiagnosticsEngine(bus, DiagnosticsCollector(resource_sampler=lambda: (None, None)))
    engine.dispose()
    # After dispose, events are no longer counted.
    bus.publish(SettingsChanged(section="x"))
    assert engine.event_count == 0
    _ = Event  # keep import used for readability


# --- log tail -------------------------------------------------------------- #
def test_tail_log_returns_last_lines(tmp_path: Path):
    log = tmp_path / "ai_caster.log"
    log.write_text("\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
    tail = tail_log(tmp_path, lines=10)
    assert len(tail) == 10
    assert tail[-1] == "line 499"


def test_tail_log_missing_dir_and_file(tmp_path: Path):
    assert tail_log(None) == []
    assert tail_log(tmp_path) == []  # no log file yet
