"""Brand helpers for the desktop UI (logo pixmap and window icon).

Thin Qt wrappers over the packaged asset in :mod:`ai_caster.ui.assets`, so views
and the main window share one source for the logo and app icon.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

from ai_caster.ui.assets import logo_path


def app_icon() -> QIcon:
    """The application/window/taskbar icon."""
    return QIcon(str(logo_path()))


def logo_pixmap(width: int = 320) -> QPixmap:
    """The brand logo scaled to ``width`` (empty pixmap if the asset is missing)."""
    pixmap = QPixmap(str(logo_path()))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
