"""A single, cohesive dark theme for the whole desktop app.

One Qt style sheet applied to the ``QApplication`` gives every view a consistent,
modern look — rounded panels, readable typography, a clear accent, and calm
surfaces — without each view having to style itself. Views may still set small
inline accents (status colours, titles); those layer on top of this base.
"""

from __future__ import annotations

# Palette — a calm dark slate with a confident blue accent.
BG = "#14171c"          # window background
SURFACE = "#1b1f27"     # panels / group boxes
ELEVATED = "#232936"    # inputs, hovered rows
BORDER = "#2b323d"      # hairlines
TEXT = "#e7ebf2"        # primary text
MUTED = "#8b94a3"       # secondary text
ACCENT = "#3d7dff"      # brand accent (buttons, selection)
ACCENT_HOVER = "#5a92ff"
ACCENT_PRESSED = "#2f68e0"
DANGER = "#e5544b"
SIDEBAR = "#12151a"

STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Inter", "Roboto", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QWidget {{ background: {BG}; }}
QMainWindow, QDialog {{ background: {BG}; }}

/* Section panels */
QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {MUTED};
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 1px;
}}

/* Buttons */
QPushButton {{
    background: {ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 14px;
    color: {TEXT};
}}
QPushButton:hover {{ background: #2b3342; border-color: #3a4150; }}
QPushButton:pressed {{ background: #1a1f29; }}
QPushButton:disabled {{ color: #5b6472; background: #191d25; border-color: #232833; }}
QPushButton:default, QPushButton#primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#primary:pressed {{ background: {ACCENT_PRESSED}; }}

/* Inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QListWidget {{
    background: {ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {ELEVATED};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
    outline: none;
}}

QLabel {{ background: transparent; }}
QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {ELEVATED};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
}}

/* Sidebar navigation */
QListWidget#nav {{
    background: {SIDEBAR};
    border: none;
    border-right: 1px solid {BORDER};
    padding: 8px 6px;
    outline: none;
}}
QListWidget#nav::item {{
    padding: 9px 12px;
    border-radius: 8px;
    margin: 1px 2px;
    color: {MUTED};
}}
QListWidget#nav::item:hover {{ background: {ELEVATED}; color: {TEXT}; }}
QListWidget#nav::item:selected {{ background: {ACCENT}; color: #ffffff; }}

/* Top account bar */
QWidget#accountBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
QWidget#accountBar QPushButton {{ padding: 5px 12px; }}

/* Progress + slider */
QProgressBar {{
    background: {ELEVATED}; border: 1px solid {BORDER};
    border-radius: 8px; text-align: center; height: 18px; color: {TEXT};
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 7px; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 14px; height: 14px;
    margin: -6px 0; border-radius: 7px;
}}

/* Scrollbars */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #40485a; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 24px; }}

QStatusBar {{ background: {SIDEBAR}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QToolTip {{
    background: {ELEVATED}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 8px;
}}
"""


def apply_theme(app) -> None:  # noqa: ANN001 - QApplication
    """Apply the app-wide dark theme to a ``QApplication``."""
    app.setStyleSheet(STYLESHEET)
