"""
NEXA UI - Application configuration

Everything installation-specific lives here: screen geometry, data paths,
and the commands used to launch the existing modality scripts.

NOTE: This file does not configure the modality algorithms themselves.
Each modality keeps its own config (e.g. the oculomotor module's config.py).
This file only says WHERE those programs are and WHAT files they produce.
"""

import os

# ---------------------------------------------------------------------------
# DISPLAY (7" Waveshare HDMI touchscreen)
# ---------------------------------------------------------------------------
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600
FULLSCREEN = True
HIDE_CURSOR = False          # set True for kiosk use with touch only
TOUCH_MIN_BUTTON_HEIGHT = 48  # minimum touch target height in px

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NEXA_ROOT = os.path.dirname(BASE_DIR)

DATA_DIR = os.path.join(NEXA_ROOT, "nexa_data")
DB_PATH = os.path.join(DATA_DIR, "nexa.sqlite3")
RAW_DATA_DIR = os.path.join(DATA_DIR, "raw")       # per-session raw modality output
REPORT_DIR = os.path.join(DATA_DIR, "reports")

# Python interpreter used to launch modality scripts
PYTHON_BIN = "python3"

# ---------------------------------------------------------------------------
# MODALITY SCRIPT LOCATIONS
# Point these at your existing, already-working modality code.
# A path that does not exist is reported as "not configured" in System Check;
# it will not crash the UI.
# ---------------------------------------------------------------------------
MODALITY_PATHS = {
    "grip":       os.path.join(NEXA_ROOT, "grip", "main.py"),
    "oculomotor": os.path.join(NEXA_ROOT, "vision", "oculomotor", "main.py"),
    "motor":      os.path.join(NEXA_ROOT, "vision", "motor", "main.py"),
    "speech":     os.path.join(NEXA_ROOT, "speech", "main.py"),
}

# Hardware devices checked on the System Check screen.
DEVICE_CHECKS = {
    "Arduino (grip)": "/dev/ttyACM0",
    "CSI camera (OV9281)": "/dev/video0",
    "USB webcam": "/dev/video1",
}

# ---------------------------------------------------------------------------
# RUNTIME BEHAVIOUR
# ---------------------------------------------------------------------------
MODALITY_TIMEOUT_S = 600      # hard ceiling; a hung modality is killed, trial marked aborted
LOG_TAIL_LINES = 400          # lines of modality stdout kept in the live log pane

# ---------------------------------------------------------------------------
# RESEARCH-USE NOTICE
# Shown on the home screen and printed on every report.
# ---------------------------------------------------------------------------
RESEARCH_NOTICE = (
    "NEXA is a research measurement instrument. It does not diagnose, screen for, "
    "or assess the severity of any disease. Outputs are raw measurements and "
    "descriptive statistics only, pending validation against reference instruments."
)


def ensure_dirs():
    for d in (DATA_DIR, RAW_DATA_DIR, REPORT_DIR):
        os.makedirs(d, exist_ok=True)