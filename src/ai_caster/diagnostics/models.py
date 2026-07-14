"""Diagnostics snapshot model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class DiagnosticsSnapshot:
    """An immutable point-in-time picture of runtime health.

    Numeric resource fields are ``None`` when the host can't report them (e.g. no
    ``psutil``), rather than a misleading zero.
    """

    uptime_seconds: float = 0.0
    event_count: int = 0

    gsi_connected: bool = False
    casting: bool = False
    muted: bool = False
    replay_active: bool = False

    capture_running: bool = False
    capture_fps: float = 0.0
    capture_drop_rate: float = 0.0

    vision_enabled: bool = False
    vision_processed: int = 0

    voice_pending_play_by_play: int = 0
    voice_pending_analyst: int = 0

    cpu_percent: float | None = None
    memory_mb: float | None = None

    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now(UTC))

    @property
    def uptime_clock(self) -> str:
        """Uptime as ``H:MM:SS`` for display."""
        total = int(self.uptime_seconds)
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}"
