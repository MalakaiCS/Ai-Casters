"""Build a :class:`FrameSource` from :class:`CaptureSettings`.

Centralises the mapping from configuration to a concrete source so the
composition root stays declarative and the choice can change at runtime by
rebuilding the source.
"""

from __future__ import annotations

from ai_caster.capture.source import FrameSource, SyntheticFrameSource
from ai_caster.config.models import CaptureSettings, CaptureSourceType
from ai_caster.core.logging import get_logger

_log = get_logger("capture.factory")


def _region(settings: CaptureSettings) -> dict | None:
    if settings.region_width > 0 and settings.region_height > 0:
        return {
            "left": settings.region_left,
            "top": settings.region_top,
            "width": settings.region_width,
            "height": settings.region_height,
        }
    return None


def create_frame_source(settings: CaptureSettings) -> FrameSource:
    """Construct the frame source described by ``settings``.

    Construction never opens the device or imports heavy dependencies — that
    happens in :meth:`FrameSource.open`, so an unavailable backend fails loudly
    only when capture is actually started.
    """
    source_type = settings.source
    if source_type is CaptureSourceType.SYNTHETIC:
        return SyntheticFrameSource(settings.width, settings.height)

    if source_type is CaptureSourceType.MONITOR:
        from ai_caster.capture.backends.monitor import MonitorFrameSource

        return MonitorFrameSource(monitor_index=settings.monitor_index, region=_region(settings))

    if source_type is CaptureSourceType.WINDOW:
        from ai_caster.capture.backends.window import WindowFrameSource

        return WindowFrameSource(window_title=settings.window_title)

    if source_type is CaptureSourceType.CAPTURE_CARD:
        from ai_caster.capture.backends.capture_card import CaptureCardFrameSource

        return CaptureCardFrameSource(
            device_index=settings.device_index,
            width=settings.width,
            height=settings.height,
        )

    _log.warning("Unknown capture source '%s'; falling back to synthetic.", source_type)
    return SyntheticFrameSource(settings.width, settings.height)
