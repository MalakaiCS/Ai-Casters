"""The diagnostics engine (Module 20 completion, M9).

Periodically samples runtime health via the :class:`DiagnosticsCollector` and
publishes a :class:`DiagnosticsUpdated` for the dashboard. It also counts events
flowing across the bus (a cheap liveness/throughput signal). Sampling runs on its
own daemon thread with an interruptible wait, so shutdown is immediate and the
engine never keeps a long broadcast from exiting cleanly.
"""

from __future__ import annotations

import threading
import time

from ai_caster.core.events import Event, EventBus
from ai_caster.core.logging import get_logger
from ai_caster.diagnostics.collector import DiagnosticsCollector
from ai_caster.diagnostics.events import DiagnosticsUpdated
from ai_caster.diagnostics.models import DiagnosticsSnapshot

_log = get_logger("diagnostics.engine")


class DiagnosticsEngine:
    """Samples and publishes runtime diagnostics on a timer."""

    def __init__(
        self,
        event_bus: EventBus,
        collector: DiagnosticsCollector,
        *,
        poll_interval: float = 2.0,
    ) -> None:
        self._bus = event_bus
        self._collector = collector
        self._interval = max(0.25, poll_interval)
        self._start_time = time.monotonic()
        self._events = 0
        self._events_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._count_unsub = event_bus.subscribe(Event, self._on_event)

    # ------------------------------------------------------------------ #
    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time

    @property
    def event_count(self) -> int:
        with self._events_lock:
            return self._events

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _on_event(self, event: Event) -> None:
        # Don't count our own publications, so the number reflects real activity.
        if isinstance(event, DiagnosticsUpdated):
            return
        with self._events_lock:
            self._events += 1

    def snapshot(self) -> DiagnosticsSnapshot:
        """Build a snapshot on demand (also used by the timer loop)."""
        return self._collector.snapshot(
            uptime_seconds=self.uptime_seconds, event_count=self.event_count
        )

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="diagnostics", daemon=True)
        self._thread.start()
        _log.info("Diagnostics engine started (every %.2fs)", self._interval)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._bus.publish(DiagnosticsUpdated(snapshot=self.snapshot()))
            except Exception:  # noqa: BLE001 - a sampling error must not kill the loop
                _log.exception("Diagnostics sampling failed")
            self._stop.wait(self._interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def dispose(self) -> None:
        self.stop()
        if self._count_unsub is not None:
            self._count_unsub()
            self._count_unsub = None
