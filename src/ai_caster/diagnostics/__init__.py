"""Module 20 completion — Diagnostics dashboard (M9).

Periodically samples runtime health (GSI, capture, vision, voice, casting state,
CPU/memory, event throughput) into an immutable snapshot published on the bus, and
tails the application log for in-app inspection. Resource figures degrade honestly
to ``None`` when the host can't report them.
"""

from ai_caster.diagnostics.collector import (
    DiagnosticsCollector,
    DiagnosticsSources,
    default_resource_sampler,
)
from ai_caster.diagnostics.engine import DiagnosticsEngine
from ai_caster.diagnostics.events import DiagnosticsUpdated
from ai_caster.diagnostics.logs import tail_log
from ai_caster.diagnostics.models import DiagnosticsSnapshot

__all__ = [
    "DiagnosticsCollector",
    "DiagnosticsSources",
    "default_resource_sampler",
    "DiagnosticsEngine",
    "DiagnosticsUpdated",
    "DiagnosticsSnapshot",
    "tail_log",
]
