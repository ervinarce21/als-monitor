"""
NEXA UI - Visual theme

Single Qt stylesheet plus a few colour constants. Tuned for a 7" 1024x600
touchscreen: high contrast, large hit targets, no hover-dependent affordances.
"""

import re

BG = "#101418"
SURFACE = "#181E25"
SURFACE_ALT = "#212A33"
BORDER = "#2E3A46"
TEXT = "#E6EDF3"
TEXT_DIM = "#8B9AA8"
ACCENT = "#3FA9F5"
ACCENT_DARK = "#2A7FBF"
OK = "#3FD08A"
WARN = "#F5B93F"
ERROR = "#F2635F"

STYLESHEET = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: "DejaVu Sans", sans-serif;
    font-size: 15px;
}}

QFrame#Sidebar {{
    background-color: {SURFACE};
    border-right: 1px solid {BORDER};
}}

QFrame#Card {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

QLabel#H1 {{ font-size: 26px; font-weight: bold; }}
QLabel#H2 {{ font-size: 20px; font-weight: bold; }}
QLabel#Dim {{ color: {TEXT_DIM}; }}
QLabel#Instruction {{
    font-size: 30px;
    font-weight: bold;
    color: {TEXT};
    padding: 18px;
}}
QLabel#Metric {{ font-size: 32px; font-weight: bold; color: {ACCENT}; }}
QLabel#MetricLabel {{ font-size: 13px; color: {TEXT_DIM}; }}
QLabel#Notice {{ color: {TEXT_DIM}; font-size: 12px; }}

QPushButton {{
    background-color: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 12px 18px;
    min-height: 24px;
}}
QPushButton:pressed {{ background-color: {BORDER}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; background-color: {SURFACE}; }}

QPushButton#Primary {{
    background-color: {ACCENT};
    color: #06202E;
    border: none;
    font-weight: bold;
}}
QPushButton#Primary:pressed {{ background-color: {ACCENT_DARK}; }}
QPushButton#Danger {{
    background-color: {ERROR};
    color: #2A0B0A;
    border: none;
    font-weight: bold;
}}
QPushButton#NavItem {{
    background: transparent;
    border: none;
    border-radius: 0px;
    text-align: left;
    padding: 16px 20px;
    font-size: 16px;
}}
QPushButton#NavItem:checked {{
    background-color: {SURFACE_ALT};
    border-left: 4px solid {ACCENT};
    font-weight: bold;
}}

QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {{
    background-color: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 10px;
    selection-background-color: {ACCENT_DARK};
}}

QTableWidget {{
    background-color: {SURFACE};
    alternate-background-color: {SURFACE_ALT};
    color: {TEXT};
    selection-background-color: {ACCENT_DARK};
    selection-color: {TEXT};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QHeaderView::section {{
    background-color: {SURFACE_ALT};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 10px;
    font-weight: bold;
}}
QTableWidget::item {{ padding: 8px; color: {TEXT}; }}
QTableWidget::item:selected {{
    background-color: {ACCENT_DARK};
    color: {TEXT};
}}

QPlainTextEdit#Log {{
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 12px;
    background-color: #0B0F13;
}}

QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    height: 22px;
}}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 5px; }}

QScrollBar:vertical {{ background: {BG}; width: 14px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 7px; min-height: 40px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0px; }}
"""


def scaled_stylesheet(scale=1.0):
    """Scale pixel dimensions for explicit user-controlled UI zoom."""
    scale = float(scale)

    def replace(match):
        value = float(match.group(1))
        return f"{max(1, round(value * scale))}px"

    return re.sub(r"(\d+(?:\.\d+)?)px", replace, STYLESHEET)
