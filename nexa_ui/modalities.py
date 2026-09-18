"""
NEXA UI - Modality registry

Declarative description of each assessment modality: how to launch the
EXISTING modality program, what the operator must set up, what the patient
is told to do, and how to read the result files that program writes.

Adding or re-pointing a modality is a data change here -- no UI code changes,
and no changes to the modality algorithms themselves.
"""

import csv
import json
import math
import os
import statistics

import config


# ---------------------------------------------------------------------------
# Metric aggregation helpers
# ---------------------------------------------------------------------------

def _numeric_column(rows, column, valid_column=None):
    """Extract a numeric column, optionally filtered by a validity flag column."""
    values = []
    for row in rows:
        if valid_column is not None:
            flag = str(row.get(valid_column, "")).strip()
            if flag not in ("1", "true", "True", "TRUE"):
                continue
        raw = str(row.get(column, "")).strip()
        if raw == "" or raw.lower() in ("nan", "none", "null"):
            continue
        try:
            values.append(float(raw))
        except ValueError:
            continue
    return values


AGGREGATORS = {
    "mean":  lambda v: statistics.mean(v) if v else None,
    "sd":    lambda v: statistics.stdev(v) if len(v) >= 2 else None,
    "cv":    lambda v: ((statistics.stdev(v) / statistics.mean(v)) * 100.0
                        if len(v) >= 2 and statistics.mean(v) else None),
    "min":   lambda v: min(v) if v else None,
    "max":   lambda v: max(v) if v else None,
    "count": lambda v: float(len(v)),
    "sum":   lambda v: float(sum(v)) if v else None,
    "last":  lambda v: v[-1] if v else None,
}


class Metric:
    """One summary number extracted from a modality's output file."""

    def __init__(self, key, label, column, agg, unit="", precision=1,
                 valid_column=None):
        self.key = key
        self.label = label
        self.column = column
        self.agg = agg
        self.unit = unit
        self.precision = precision
        self.valid_column = valid_column

    def compute(self, rows):
        values = _numeric_column(rows, self.column, self.valid_column)
        fn = AGGREGATORS.get(self.agg)
        if fn is None:
            return None
        try:
            return fn(values)
        except statistics.StatisticsError:
            return None

    def format(self, value):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return "—"
        text = f"{value:.{self.precision}f}"
        return f"{text} {self.unit}".strip()


class Modality:
    def __init__(self, key, name, subtitle, output_files, metrics,
                 operator_checklist, patient_instruction, patient_detail="",
                 args=None, est_duration_s=60, passage_text=""):
        self.key = key
        self.name = name
        self.subtitle = subtitle
        self.output_files = output_files
        self.metrics = metrics
        self.operator_checklist = operator_checklist
        self.patient_instruction = patient_instruction
        self.patient_detail = patient_detail
        self.args = args or []
        self.est_duration_s = est_duration_s
        self.passage_text = passage_text

    # -- launching -------------------------------------------------------

    @property
    def script_path(self):
        return config.MODALITY_MODULES.get(self.key, "")

    @property
    def working_dir(self):
        return config.NEXA_ROOT

    def is_available(self):
        module = self.script_path
        if not module or not os.path.isdir(config.SOURCE_DIR):
            return False
        package_path = os.path.join(config.SOURCE_DIR, *module.split("."))
        return os.path.isfile(os.path.join(package_path, "__main__.py"))

    def build_command(self):
        """Command list to hand to QProcess. The existing script is run as-is."""
        return [config.PYTHON_BIN, "-m", self.script_path] + list(self.args)

    # -- result reading -------------------------------------------------------

    def collect_output_files(self, output_dir=None):
        """Absolute paths of result files that actually exist after a run."""
        found = []
        base = output_dir or self.working_dir
        for fname in self.output_files:
            candidate = os.path.join(base, fname)
            if os.path.isfile(candidate):
                found.append(candidate)
        return found

    def parse_metrics(self, output_paths):
        """
        Read the modality's own output files and compute the declared summary
        metrics. Prefers a JSON sidecar if the script wrote one; otherwise
        aggregates the CSV.
        """
        rows = []
        direct = {}

        for path in output_paths:
            ext = os.path.splitext(path)[1].lower()
            try:
                if ext == ".json":
                    with open(path, "r") as f:
                        payload = json.load(f)
                    if isinstance(payload, dict):
                        direct.update(payload)
                elif ext == ".csv":
                    with open(path, "r", newline="") as f:
                        rows.extend(list(csv.DictReader(f)))
            except (OSError, json.JSONDecodeError, csv.Error):
                continue

        metrics = {}
        for metric in self.metrics:
            if metric.key in direct:
                try:
                    metrics[metric.key] = float(direct[metric.key])
                except (TypeError, ValueError):
                    metrics[metric.key] = None
            else:
                metrics[metric.key] = metric.compute(rows)
        for key in ("task", "quality_status", "quality_flags"):
            if key in direct:
                metrics[key] = direct[key]
        return metrics

    def format_metrics(self, metrics):
        """Returns list of (label, formatted_value) for display."""
        out = []
        for metric in self.metrics:
            out.append((metric.label, metric.format(metrics.get(metric.key))))
        return out


# ---------------------------------------------------------------------------
# REGISTRY
#
# Adjust output_files / metric column names here to match what each of your
# existing modality scripts actually writes.
# ---------------------------------------------------------------------------

GRIP = Modality(
    key="grip",
    name="Grip Strength",
    subtitle="Dual load cell — maximal force and short-duration grip-force consistency",
    output_files=["grip_summary.json"],
    metrics=[
        Metric("peak_left", "Peak force (L)", "peak_left", "last", "N", 2),
        Metric("peak_right", "Peak force (R)", "peak_right", "last", "N", 2),
        Metric("duration", "Duration", "duration", "last", "s", 1),
    ],
    operator_checklist=[
        "Arduino Uno connected and enumerated (see System Check).",
        "Both load cells zeroed/tared with no load applied.",
        "Participant seated, elbow at ~90°, forearm supported, wrist neutral.",
        "Dynamometer handle adjusted to hand size.",
    ],
    patient_instruction="Squeeze as hard as you can",
    patient_detail=(
        "When told to start, squeeze the handle as hard as you can and hold it "
        "steady until you are told to stop. Keep your arm still."
    ),
    est_duration_s=120,
)

OCULOMOTOR = Modality(
    key="oculomotor",
    name="Oculomotor",
    subtitle="Visually guided prosaccade latency (OV9281 IR camera)",
    output_files=["eye_results.csv", "eye_summary.json"],
    metrics=[
        Metric("valid_trials", "Valid trials", "valid", "sum", "", 0),
        Metric("mean_latency_ms", "Mean latency", "prosaccade_latency_ms", "mean",
               "ms", 1, valid_column="valid"),
        Metric("sd_latency_ms", "SD", "prosaccade_latency_ms", "sd",
               "ms", 1, valid_column="valid"),
        Metric("cv_percent", "CV", "prosaccade_latency_ms", "cv",
               "%", 1, valid_column="valid"),
    ],
    operator_checklist=[
        "OV9281 camera aimed at the tracked eye; pupil clearly visible in frame.",
        "IR illumination stable; no direct sunlight or flickering light source.",
        "Head position stable (chin rest or headrest) at the intended viewing distance.",
        "Room lighting will stay constant for the whole run.",
    ],
    patient_instruction="Look at the dot in the centre, then at the new dot",
    patient_detail=(
        "Keep your eyes on the centre dot. When a new dot appears to the side, "
        "look at it as quickly as you can. Then return to the centre dot."
    ),
    est_duration_s=60,
)

MOTOR = Modality(
    key="motor",
    name="Motor / Movement",
    subtitle="Camera-based movement analysis (USB webcam)",
    output_files=["shoulder_summary.json"],
    metrics=[
        Metric("peak_velocity", "Peak angular velocity", "peak_velocity", "last", "deg/s", 1),
    ],
    operator_checklist=[
        "USB webcam connected and framing the full movement.",
        "Participant's limb fully inside frame throughout the movement range.",
        "Background uncluttered; consistent lighting.",
        "Task demonstrated to the participant once before recording.",
    ],
    patient_instruction="Repeat the movement as quickly and evenly as you can",
    patient_detail=(
        "Perform the movement you were just shown. Keep going at a steady, quick "
        "pace until you are told to stop."
    ),
    est_duration_s=90,
)

SPEECH = Modality(
    key="speech",
    name="Speech",
    subtitle="Microphone-based speech analysis (USB conference mic)",
    output_files=["speech_recording.wav", "speech_summary.json"],
    metrics=[
        Metric("recording_duration_sec", "Recording length", "recording_duration_sec", "last", "s", 1),
        Metric("speech_duration_sec", "Speech duration", "speech_duration_sec", "last", "s", 1),
        Metric("pause_percentage", "Pause percentage", "pause_percentage", "last", "%", 1),
        Metric("mean_f0_hz", "Mean F0", "mean_f0_hz", "last", "Hz", 1),
        Metric("hnr_db", "HNR", "hnr_db", "last", "dB", 1),
    ],
    operator_checklist=[
        "USB microphone connected and selected as the input device.",
        "Mic positioned at a consistent distance from the participant.",
        "Room quiet; fans, aircon, and other devices accounted for.",
        "Participant has heard the task instruction and confirmed understanding.",
    ],
    patient_instruction="Speak when the recording starts",
    patient_detail=(
        "Follow the spoken task instruction. Speak clearly at a comfortable "
        "volume and keep going until you are told to stop."
    ),
    args=["assess", "--duration", "10"],
    est_duration_s=20,
)


SPEECH_TASKS = {
    "connected_speech": {
        "name": "Connected Speech",
        "subtitle": "Continuous speech timing and acoustic assessment",
        "instruction": "Speak naturally about a familiar topic",
        "detail": (
            "Continue speaking at a comfortable pace and volume until the "
            "recording ends."
        ),
        "duration": 30,
    },
    "sustained_vowel": {
        "name": "Sustained Vowel",
        "subtitle": "Sustained vowel phonation assessment",
        "instruction": "Take a breath and hold the sound 'ah'",
        "detail": (
            "Use a comfortable pitch and volume, and sustain the sound steadily "
            "until the recording ends."
        ),
        "duration": 5,
    },
    "reading": {
        "name": "Reading",
        "subtitle": "Fixed-passage speech timing assessment",
        "instruction": "Rainbow Passage",
        "detail": "Read the complete passage shown below.",
        "duration": 60,
    },
}


RAINBOW_PASSAGE_PATH = os.path.join(
    config.SOURCE_DIR, "als_monitor", "speech_analysis", "passages",
    "rainbow_passage.txt",
)
try:
    with open(RAINBOW_PASSAGE_PATH, "r", encoding="utf-8") as passage_file:
        RAINBOW_PASSAGE = passage_file.read().strip()
except OSError:
    RAINBOW_PASSAGE = "Rainbow Passage file is unavailable."


def speech_modality(task, wav_path=None):
    """Build a speech runner configuration for a task or existing WAV."""
    spec = SPEECH_TASKS[task]
    if wav_path:
        commands = {
            "connected_speech": "analyze-speech",
            "sustained_vowel": "analyze-sustained-vowel",
            "reading": "analyze-reading",
        }
        args = [commands[task], wav_path]
        name = f"Analyze WAV - {spec['name']}"
        subtitle = "Analyze and attach an existing WAV recording"
        instruction = "Confirm the selected recording and analysis type"
        detail = os.path.basename(wav_path)
        duration = 10
    else:
        args = ["assess", "--task", task, "--duration", str(spec["duration"])]
        name = spec["name"]
        subtitle = spec["subtitle"]
        instruction = spec["instruction"]
        detail = spec["detail"]
        duration = spec["duration"]

    return Modality(
        key="speech",
        name=name,
        subtitle=subtitle,
        output_files=list(SPEECH.output_files),
        metrics=list(SPEECH.metrics),
        operator_checklist=list(SPEECH.operator_checklist),
        patient_instruction=instruction,
        patient_detail=detail,
        args=args,
        est_duration_s=duration,
        passage_text=(RAINBOW_PASSAGE if task == "reading" and not wav_path else ""),
    )

REGISTRY = [GRIP, OCULOMOTOR, MOTOR, SPEECH]
BY_KEY = {m.key: m for m in REGISTRY}


def get(key):
    return BY_KEY.get(key)
