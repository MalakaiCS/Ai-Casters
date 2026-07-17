"""Collects a :class:`DiagnosticsSnapshot` from the running subsystems.

The collector reads state through a bundle of small **accessor callables**
(:class:`DiagnosticsSources`) rather than importing the subsystems, which keeps it
fully decoupled and trivially testable with fakes. Resource sampling (CPU/memory)
uses ``psutil`` when available and degrades to the stdlib (memory only) or to
``None`` — never a fabricated figure.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field

from ai_caster.capture.timing import CaptureStats
from ai_caster.diagnostics.models import DiagnosticsSnapshot


@dataclass
class DiagnosticsSources:
    """Accessor callables the collector samples. All have safe defaults."""

    gsi_connected: Callable[[], bool] = lambda: False
    capture_stats: Callable[[], CaptureStats | None] = lambda: None
    vision_enabled: Callable[[], bool] = lambda: False
    vision_processed: Callable[[], int] = lambda: 0
    voice_pending: Callable[[], tuple[int, int]] = lambda: (0, 0)
    replay_active: Callable[[], bool] = lambda: False
    casting: Callable[[], bool] = lambda: False
    muted: Callable[[], bool] = lambda: False


ResourceSampler = Callable[[], tuple[float | None, float | None]]


def default_resource_sampler() -> tuple[float | None, float | None]:
    """Return ``(cpu_percent, memory_mb)`` — best available, honest about gaps."""
    if importlib.util.find_spec("psutil") is not None:
        import psutil  # type: ignore

        process = psutil.Process()
        # cpu_percent(None) is non-blocking and reports since the last call.
        cpu = float(process.cpu_percent(None))
        memory = float(process.memory_info().rss) / (1024 * 1024)
        return cpu, memory

    # Stdlib fallback: resident memory only (Linux reports KB, macOS bytes).
    try:  # pragma: no cover - platform dependent
        import resource
        import sys

        maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        memory_mb = maxrss / 1024 if sys.platform == "linux" else maxrss / (1024 * 1024)
        return None, float(memory_mb)
    except Exception:  # noqa: BLE001 - resource unavailable (e.g. Windows)
        return None, None


@dataclass
class DiagnosticsCollector:
    """Builds snapshots from the configured sources and a resource sampler."""

    sources: DiagnosticsSources = field(default_factory=DiagnosticsSources)
    resource_sampler: ResourceSampler = default_resource_sampler

    def snapshot(self, *, uptime_seconds: float, event_count: int) -> DiagnosticsSnapshot:
        stats = self.sources.capture_stats()
        pending_pbp, pending_analyst = self.sources.voice_pending()
        cpu, memory = self.resource_sampler()
        return DiagnosticsSnapshot(
            uptime_seconds=uptime_seconds,
            event_count=event_count,
            gsi_connected=bool(self.sources.gsi_connected()),
            casting=bool(self.sources.casting()),
            muted=bool(self.sources.muted()),
            replay_active=bool(self.sources.replay_active()),
            capture_running=bool(stats.running) if stats else False,
            capture_fps=float(stats.actual_fps) if stats else 0.0,
            capture_drop_rate=float(stats.drop_rate) if stats else 0.0,
            vision_enabled=bool(self.sources.vision_enabled()),
            vision_processed=int(self.sources.vision_processed()),
            voice_pending_play_by_play=int(pending_pbp),
            voice_pending_analyst=int(pending_analyst),
            cpu_percent=cpu,
            memory_mb=memory,
        )
