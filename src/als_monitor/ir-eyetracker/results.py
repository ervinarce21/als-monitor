"""
Trial storage, CSV export and summary statistics.

Measurement only: no classification, no diagnosis, no clinical thresholds.
"""

import csv
import math
import os
import statistics
from dataclasses import dataclass, field
from datetime import datetime

import config


@dataclass
class TrialResult:
    trial: int
    direction: str
    target_onset_timestamp: float          # perf_counter seconds
    saccade_onset_timestamp: float
    prosaccade_latency_ms: float
    confidence: float
    valid: bool
    reason: str = ""
    n_samples: int = 0
    median_interval_ms: float = float("nan")
    peak_velocity: float = float("nan")
    samples: list = field(default_factory=list, repr=False)


def _fmt(value, digits=3):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, float):
        return "%.*f" % (digits, value)
    return value


def timestamped_path(prefix, extension="csv"):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = "%s_%s_%s.%s" % (prefix, config.PARTICIPANT_ID, stamp, extension)
    return os.path.join(config.OUTPUT_DIR, name)


def save_results_csv(trials, path=None):
    """Write the per-trial CSV. Returns the path, or None on failure."""
    path = path or timestamped_path("prosaccade")
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "trial", "direction", "target_onset_timestamp",
                "saccade_onset_timestamp", "prosaccade_latency_ms",
                "confidence", "valid", "reason", "n_samples",
                "median_sample_interval_ms", "peak_velocity_px_s",
            ])
            for tr in trials:
                writer.writerow([
                    tr.trial,
                    tr.direction,
                    _fmt(tr.target_onset_timestamp, 6),
                    _fmt(tr.saccade_onset_timestamp, 6),
                    _fmt(tr.prosaccade_latency_ms, 1),   # blank if not detected
                    _fmt(tr.confidence, 2),
                    1 if tr.valid else 0,
                    tr.reason,
                    tr.n_samples,
                    _fmt(tr.median_interval_ms, 2),
                    _fmt(tr.peak_velocity, 1),
                ])
        return path
    except OSError as exc:
        print("[results] Could not write CSV (%s): %s" % (path, exc))
        return None


def save_raw_samples_csv(trials, path=None):
    """Optional per-frame pupil trace, one row per sample."""
    if not config.SAVE_RAW_SAMPLES:
        return None
    path = path or timestamped_path("prosaccade_samples")
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["trial", "direction", "frame_timestamp",
                             "time_from_target_onset_ms", "pupil_x", "pupil_y",
                             "confidence", "found"])
            for tr in trials:
                for s in tr.samples:
                    writer.writerow([
                        tr.trial, tr.direction, _fmt(s.timestamp, 6),
                        _fmt((s.timestamp - tr.target_onset_timestamp) * 1000.0, 2),
                        _fmt(s.x, 2), _fmt(s.y, 2), _fmt(s.confidence, 2),
                        1 if s.found else 0,
                    ])
        return path
    except OSError as exc:
        print("[results] Could not write sample CSV (%s): %s" % (path, exc))
        return None


def summarise(trials):
    """Basic descriptive statistics over valid trials."""
    latencies = [t.prosaccade_latency_ms for t in trials
                 if t.valid and not math.isnan(t.prosaccade_latency_ms)]
    summary = {
        "total_trials": len(trials),
        "valid_trials": len(latencies),
        "invalid_trials": len(trials) - len(latencies),
        "mean_latency_ms": float("nan"),
        "sd_latency_ms": float("nan"),
        "cv_percent": float("nan"),
        "min_latency_ms": float("nan"),
        "max_latency_ms": float("nan"),
    }
    if latencies:
        summary["mean_latency_ms"] = statistics.fmean(latencies)
        summary["min_latency_ms"] = min(latencies)
        summary["max_latency_ms"] = max(latencies)
    if len(latencies) >= 2:
        sd = statistics.stdev(latencies)
        summary["sd_latency_ms"] = sd
        if summary["mean_latency_ms"] > 0:
            summary["cv_percent"] = 100.0 * sd / summary["mean_latency_ms"]
    return summary


def save_summary_csv(summary, path=None):
    path = path or timestamped_path("prosaccade_summary")
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["metric", "value"])
            for key, value in summary.items():
                writer.writerow([key, _fmt(value, 2)])
        return path
    except OSError as exc:
        print("[results] Could not write summary CSV (%s): %s" % (path, exc))
        return None


def print_summary(summary):
    print("\n--- Prosaccade latency summary ---")
    print("Valid trials : %d / %d" % (summary["valid_trials"],
                                      summary["total_trials"]))
    if summary["valid_trials"]:
        print("Mean latency : %.1f ms" % summary["mean_latency_ms"])
    if not math.isnan(summary["sd_latency_ms"]):
        print("SD           : %.1f ms" % summary["sd_latency_ms"])
    if not math.isnan(summary["cv_percent"]):
        print("CV           : %.1f %%" % summary["cv_percent"])
    print("----------------------------------")