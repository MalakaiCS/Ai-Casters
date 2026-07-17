"""Concrete frame-source backends for real observer feeds.

Each backend lazily imports its heavy/OS-specific dependency (mss, OpenCV,
window-manager bindings) inside ``open()``. Importing this package therefore
costs nothing and never fails for a missing capture dependency; a clear
:class:`RuntimeError` is raised only if you actually try to *open* a source
whose dependency is absent.
"""

from ai_caster.capture.backends.capture_card import CaptureCardFrameSource
from ai_caster.capture.backends.monitor import MonitorFrameSource
from ai_caster.capture.backends.window import WindowFrameSource

__all__ = ["MonitorFrameSource", "WindowFrameSource", "CaptureCardFrameSource"]
