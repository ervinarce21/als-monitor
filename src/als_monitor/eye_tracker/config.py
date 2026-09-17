"""
NEXA - oculomotor module configuration.

Single place for every tunable parameter. Nothing important is hard-coded
deeper in the code base.
"""

# =====================================================================
# SECTION A - HARDWARE UNCERTAINTY
# Different OV9281 carrier boards / libcamera versions expose slightly
# different pixel formats and controls. Everything that depends on that
# lives here and NOWHERE else.
# =====================================================================
CAMERA_WIDTH = 640          # OV9281 native is 1280x800; 640x400 is a fast crop/bin
CAMERA_HEIGHT = 400
CAMERA_FPS = 120            # requested frame rate (FrameDurationLimits)

# Pixel format requested from Picamera2 for the "main" stream.
# "YUV420" is the most widely supported; the Y plane is used as grayscale.
# Alternatives that some builds expose for mono sensors: "R8", "GREY", "RGB888".
CAMERA_FORMAT = "YUV420"

# Manual exposure/gain keeps image brightness constant during the test.
CAMERA_MANUAL_EXPOSURE = True
CAMERA_EXPOSURE_US = 4000        # microseconds; must be < 1e6 / CAMERA_FPS
CAMERA_ANALOGUE_GAIN = 4.0
CAMERA_HFLIP = False
CAMERA_VFLIP = False

# Use the sensor timestamp from frame metadata when available.
# Falls back to a monotonic timestamp taken when the frame is received.
CAMERA_USE_SENSOR_TIMESTAMP = True
CAMERA_WARMUP_S = 1.0            # let AE/AGC settle before sampling

# =====================================================================
# SECTION B - EYE SELECTION / IMAGE GEOMETRY
# =====================================================================
EYE = "right"                    # "right" | "left" | "single"
# How the chosen eye is isolated in the frame:
#   "full"  -> the camera already frames one eye only (typical OV9281 eye cam)
#   "half"  -> both eyes visible; use the image half matching EYE
EYE_ROI_MODE = "full"

# Mapping from SCREEN direction to IMAGE-coordinate direction.
# Image x grows to the right, image y grows downward.
# If the camera image is mirrored relative to the participant's view,
# set DIR_SIGN_X = -1. Verify once with the debug preview, then leave alone.
DIR_SIGN_X = 1
DIR_SIGN_Y = 1

# =====================================================================
# SECTION C - PUPIL DETECTION
# =====================================================================
PROCESS_SCALE = 1.0              # <1.0 downscales frames before CV (speed)
BLUR_KERNEL = 5                  # odd number, Gaussian blur before threshold

# "percentile" adapts to illumination; "fixed" uses PUPIL_THRESHOLD directly.
PUPIL_THRESHOLD_MODE = "percentile"
PUPIL_THRESHOLD = 45             # 0-255, used when mode == "fixed"
PUPIL_DARK_PERCENTILE = 2.0      # used when mode == "percentile"
PUPIL_THRESHOLD_OFFSET = 12      # added to the percentile value
PUPIL_THRESHOLD_MIN = 10
PUPIL_THRESHOLD_MAX = 110

MORPH_KERNEL = 5                 # ellipse structuring element size
MORPH_OPEN_ITER = 1
MORPH_CLOSE_ITER = 2

PUPIL_MIN_AREA = 150             # px^2, in processing-scale pixels
PUPIL_MAX_AREA = 20000
PUPIL_MIN_CIRCULARITY = 0.55     # 4*pi*A / P^2
PUPIL_MIN_FILL = 0.45            # area / minEnclosingCircle area
PUPIL_MIN_CONFIDENCE = 0.35      # samples below this are treated as "not found"

# =====================================================================
# SECTION D - CALIBRATION
# =====================================================================
CALIBRATION_DURATION_S = 3.0
CALIBRATION_MIN_DETECTION_RATE = 0.60   # fraction of frames with a pupil
CALIBRATION_MAX_NOISE_PX = 6.0          # SD of pupil position while fixating
CALIBRATION_ALLOW_CONTINUE = True       # allow operator to proceed anyway

# =====================================================================
# SECTION E - TRIAL STRUCTURE
# =====================================================================
NUM_TRIALS = 10
FIXATION_DURATION_S = 1.0
FIXATION_JITTER_S = 0.3          # random extra 0..jitter, prevents anticipation
POST_TARGET_WINDOW_S = 1.0       # how long the eye is watched after target onset
INTER_TRIAL_INTERVAL_S = 1.0
TARGET_DIRECTIONS = ["left", "right", "up", "down"]
RANDOM_SEED = None               # int for reproducible direction order

# =====================================================================
# SECTION F - DISPLAY
# =====================================================================
SCREEN_WIDTH = 1024              # Waveshare 7in HDMI panel
SCREEN_HEIGHT = 600
FULLSCREEN = True
BACKGROUND_COLOR = (0, 0, 0)
FIXATION_COLOR = (200, 200, 200)
TARGET_COLOR = (255, 255, 255)
FIXATION_RADIUS_PX = 8
TARGET_RADIUS_PX = 10
TARGET_OFFSET_PX = 300           # distance from screen centre to target
SHOW_TRIAL_NUMBER = True         # small, dim, corner of the screen
DISPLAY_LATENCY_COMPENSATION_MS = 0.0   # measured panel/render lag, if known
DEBUG_PREVIEW = False            # show the camera view + pupil marker (setup only)
VIDEO_FEEDBACK = True            # live camera check before calibration
VIDEO_FEEDBACK_FPS = 30          # display refresh rate; capture still runs at CAMERA_FPS
VIDEO_FEEDBACK_MAX_WIDTH = 720
VIDEO_FEEDBACK_MAX_HEIGHT = 450

# =====================================================================
# SECTION G - SIGNAL PROCESSING / SACCADE DETECTION
# =====================================================================
SMOOTHING_WINDOW = 3             # moving-average samples; keep small (latency!)
BASELINE_DURATION_S = 0.30       # window before target onset used as baseline
MIN_BASELINE_SAMPLES = 8

VELOCITY_THRESHOLD = 120.0       # px/s, absolute floor for the threshold
BASELINE_SD_MULTIPLIER = 5.0     # adaptive part: mean + k*SD of baseline velocity
MIN_SACCADE_DURATION = 0.020     # s, condition must hold this long
MIN_CONSECUTIVE_SAMPLES = 3      # ...and for at least this many samples
MIN_DISPLACEMENT = 6.0           # px, signed displacement along the target axis
MAX_OFF_AXIS_RATIO = 1.5         # reject if off-axis motion dominates this much

MIN_LATENCY_S = 0.070            # below this = anticipatory, rejected
MAX_LATENCY_S = 0.800            # above this = no valid saccade
DISPLACEMENT_CHECK_WINDOW_S = 0.150   # window after onset used for direction check

# Timing sanity: if the achieved sampling interval is worse than this the
# trial is marked invalid instead of producing a misleading latency.
MAX_MEDIAN_SAMPLE_INTERVAL_S = 0.025   # 25 ms == 40 Hz
MIN_SAMPLES_IN_WINDOW = 15

# =====================================================================
# SECTION H - OUTPUT
# =====================================================================
OUTPUT_DIR = "results"
SAVE_RAW_SAMPLES = True          # also write the per-frame pupil trace
PARTICIPANT_ID = "anonymous"
