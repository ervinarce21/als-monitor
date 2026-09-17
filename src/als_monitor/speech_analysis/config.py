"""
NEXA speech module - central configuration.

Every tunable parameter for recording, VAD/segmentation, acoustic analysis
and quality control lives here. Nothing else in the codebase should
hard-code these values.

ASSUMPTIONS (labelled explicitly, change as needed for your setup):
- ASSUMPTION: the USB microphone is the default input device on the Pi.
  Use `als-monitor speech list-microphones` to confirm and
  set MIC_DEVICE_INDEX below if it is not.
- ASSUMPTION: 300 ms is used as an initial, configurable research
  parameter for pause detection, NOT a validated clinical cutoff.
"""

from pathlib import Path

# =====================================================================
# PROJECT PATHS
# =====================================================================
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "speech_analysis"
RECORDINGS_DIR = DATA_DIR / "recordings"
RESULTS_DIR = DATA_DIR / "results"
LOGS_DIR = DATA_DIR / "logs"
PASSAGES_DIR = DATA_DIR / "passages"
DATABASE_DIR = DATA_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "nexa_speech.db"
SCHEMA_PATH = PACKAGE_DIR / "schema.sql"

for _dir in (RECORDINGS_DIR, RESULTS_DIR, LOGS_DIR, PASSAGES_DIR,
             DATABASE_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# =====================================================================
# AUDIO RECORDING
# =====================================================================
SAMPLE_RATE = 44100          # Hz
CHANNELS = 1                 # mono
SAMPLE_WIDTH_BITS = 16       # PCM16
SUBTYPE = "PCM_16"           # soundfile subtype string
RECORDING_FORMAT = "WAV"

# None = use the system default input device. Set to an integer device
# index (from --list-microphones) if the wrong device gets selected.
MIC_DEVICE_INDEX = None

# Safety cap so an accidental "record forever" cannot fill the disk.
MAX_RECORDING_SECONDS = 180

# =====================================================================
# TASKS
# =====================================================================
TASK_SUSTAINED_VOWEL = "sustained_vowel"
TASK_CONNECTED_SPEECH = "connected_speech"

SUSTAINED_VOWEL_MIN_SECONDS = 2.0    # below this, quality check warns
SUSTAINED_VOWEL_TARGET_SECONDS = 5.0

DEFAULT_PASSAGE_PATH = PASSAGES_DIR / "rainbow_passage.txt"
DEFAULT_PASSAGE_METADATA_PATH = PASSAGES_DIR / "rainbow_passage_metadata.json"

# =====================================================================
# VOICE ACTIVITY DETECTION / SEGMENTATION  (implemented in STEP 5)
# =====================================================================
# Research parameter, not a clinical cutoff - validate for your task/population.
PAUSE_THRESHOLD_SECONDS = 0.300
MIN_SPEECH_SEGMENT_SECONDS = 0.100
MIN_PAUSE_DURATION_SECONDS = 0.150
VAD_FRAME_DURATION_MS = 30           # 10/20/30 ms required by WebRTC VAD
VAD_AGGRESSIVENESS = 2               # WebRTC VAD: 0 (least) - 3 (most aggressive)

# =====================================================================
# F0 ANALYSIS (Praat/Parselmouth)  (implemented in STEP 6)
# =====================================================================
F0_PITCH_FLOOR_HZ = 75.0
F0_PITCH_CEILING_HZ = 500.0
F0_TIME_STEP = 0.0            # 0.0 = Praat default (= 0.75 / floor)
F0_MIN_VALID_FRAME_PERCENT = 30.0   # below this, flag INVALID_F0

# =====================================================================
# HNR ANALYSIS (Praat/Parselmouth)  (implemented in STEP 7)
# =====================================================================
HNR_TIME_STEP = 0.01
HNR_MIN_PITCH_HZ = 75.0
HNR_SILENCE_THRESHOLD = 0.1
HNR_PERIODS_PER_WINDOW = 1.0
HNR_MIN_VALID_FRAME_PERCENT = 30.0  # below this, flag INVALID_HNR

# =====================================================================
# AUDIO QUALITY CONTROL  (implemented in STEP 4)
# =====================================================================
QC_MIN_DURATION_SECONDS = 1.0
QC_MIN_RMS_DBFS = -45.0        # quieter than this -> TOO_QUIET
QC_CLIPPING_SAMPLE_FRACTION = 0.001   # fraction of samples at full scale
QC_MIN_SPEECH_DURATION_SECONDS = 1.0  # for connected speech

QUALITY_VALID = "VALID"
QUALITY_WARNING = "WARNING"
QUALITY_REJECTED = "REJECTED"

# Quality flag identifiers used across the pipeline.
QF_MICROPHONE_NOT_FOUND = "MICROPHONE_NOT_FOUND"
QF_EMPTY_AUDIO = "EMPTY_AUDIO"
QF_TOO_SHORT = "TOO_SHORT"
QF_TOO_QUIET = "TOO_QUIET"
QF_EXCESSIVE_NOISE = "EXCESSIVE_NOISE"
QF_CLIPPING_DETECTED = "CLIPPING_DETECTED"
QF_INSUFFICIENT_SPEECH = "INSUFFICIENT_SPEECH"
QF_INSUFFICIENT_VOICED_FRAMES = "INSUFFICIENT_VOICED_FRAMES"
QF_INVALID_F0 = "INVALID_F0"
QF_INVALID_HNR = "INVALID_HNR"
QF_VAD_FAILURE = "VAD_FAILURE"
QF_WAV_FORMAT_ERROR = "WAV_FORMAT_ERROR"

# =====================================================================
# APPLICATION / VERSIONING
# =====================================================================
NEXA_SPEECH_MODULE_VERSION = "0.1.0-step1"
PARTICIPANT_ID_DEFAULT = "P000"
