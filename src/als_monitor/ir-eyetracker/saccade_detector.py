"""
Saccade onset detection.

raw pupil positions -> valid-point filtering -> light smoothing ->
velocity -> baseline estimation -> sustained-threshold crossing ->
direction validation -> onset time.

Deliberately conservative: when anything is doubtful the trial is returned
as invalid rather than producing a latency that cannot be trusted.
"""

import math
from dataclasses import dataclass

import numpy as np

import config


@dataclass
class SaccadeResult:
    valid: bool
    saccade_onset_time: float = float("nan")   # perf_counter seconds
    latency_ms: float = float("nan")
    confidence: float = 0.0                    # mean pupil-detection confidence
    peak_velocity: float = float("nan")        # px/s, diagnostic only
    threshold_used: float = float("nan")
    n_samples: int = 0
    median_interval_ms: float = float("nan")
    reason: str = ""


# ----------------------------------------------------------------------
# Direction handling
# ----------------------------------------------------------------------
def direction_axis(direction):
    """
    Unit vector, in IMAGE coordinates, that the pupil should move along for
    the given SCREEN direction. Image y grows downward.
    """
    sx, sy = config.DIR_SIGN_X, config.DIR_SIGN_Y
    return {
        "left":  (-sx, 0.0),
        "right": (sx, 0.0),
        "up":    (0.0, -sy),
        "down":  (0.0, sy),
    }[direction]


# ----------------------------------------------------------------------
# Signal processing helpers
# ----------------------------------------------------------------------
def _moving_average(values, window):
    """Centred moving average that keeps the array length."""
    window = int(window)
    if window <= 1 or values.size < window:
        return values.astype(float)
    kernel = np.ones(window, dtype=float) / window
    padded = np.pad(values.astype(float), (window // 2, window - 1 - window // 2),
                    mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _velocity(t, x, y):
    """Central-difference speed in px/s (forward/backward at the edges)."""
    n = t.size
    v = np.zeros(n, dtype=float)
    if n < 2:
        return v
    for i in range(n):
        lo = max(0, i - 1)
        hi = min(n - 1, i + 1)
        dt = t[hi] - t[lo]
        if dt <= 0:
            v[i] = 0.0
            continue
        v[i] = math.hypot(x[hi] - x[lo], y[hi] - y[lo]) / dt
    return v


# ----------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------
def detect_saccade(samples, target_onset_time, direction):
    """
    samples            : list of PupilSample covering baseline + post-target
    target_onset_time  : perf_counter seconds of target presentation
    direction          : "left" | "right" | "up" | "down"
    """
    valid_samples = [s for s in samples
                     if s.found and not math.isnan(s.x) and not math.isnan(s.y)]
    if len(valid_samples) < config.MIN_SAMPLES_IN_WINDOW:
        return SaccadeResult(False, n_samples=len(valid_samples),
                             reason="insufficient_valid_samples")

    t = np.array([s.timestamp for s in valid_samples], dtype=float)
    x_raw = np.array([s.x for s in valid_samples], dtype=float)
    y_raw = np.array([s.y for s in valid_samples], dtype=float)
    conf = np.array([s.confidence for s in valid_samples], dtype=float)

    intervals = np.diff(t)
    median_dt = float(np.median(intervals)) if intervals.size else float("nan")
    if not np.isfinite(median_dt) or median_dt > config.MAX_MEDIAN_SAMPLE_INTERVAL_S:
        return SaccadeResult(False, n_samples=t.size,
                             median_interval_ms=median_dt * 1000.0,
                             reason="sampling_too_slow")

    x = _moving_average(x_raw, config.SMOOTHING_WINDOW)
    y = _moving_average(y_raw, config.SMOOTHING_WINDOW)
    v = _velocity(t, x, y)

    # ---- baseline from the fixation period immediately before onset -----
    base_mask = (t >= target_onset_time - config.BASELINE_DURATION_S) & \
                (t <= target_onset_time)
    if int(np.count_nonzero(base_mask)) < config.MIN_BASELINE_SAMPLES:
        return SaccadeResult(False, n_samples=t.size,
                             median_interval_ms=median_dt * 1000.0,
                             reason="insufficient_baseline")

    base_x = float(np.median(x[base_mask]))
    base_y = float(np.median(y[base_mask]))
    base_v = v[base_mask]
    threshold = max(config.VELOCITY_THRESHOLD,
                    float(np.mean(base_v) +
                          config.BASELINE_SD_MULTIPLIER * np.std(base_v)))

    axis_x, axis_y = direction_axis(direction)

    # ---- search for a sustained, correctly directed velocity increase ---
    search = np.where((t >= target_onset_time + config.MIN_LATENCY_S) &
                      (t <= target_onset_time + config.MAX_LATENCY_S))[0]
    if search.size == 0:
        return SaccadeResult(False, n_samples=t.size,
                             threshold_used=threshold,
                             median_interval_ms=median_dt * 1000.0,
                             reason="no_post_target_samples")

    i = int(search[0])
    last = int(search[-1])
    peak_velocity = float(np.max(v[search]))

    while i <= last:
        if v[i] <= threshold:
            i += 1
            continue

        # Extend the run of supra-threshold samples.
        j = i
        while j + 1 < t.size and v[j + 1] > threshold:
            j += 1
        run_samples = j - i + 1
        run_duration = t[j] - t[i]

        if (run_samples >= config.MIN_CONSECUTIVE_SAMPLES and
                run_duration >= config.MIN_SACCADE_DURATION):
            if _direction_ok(t, x, y, i, base_x, base_y, axis_x, axis_y):
                window = (t >= t[i]) & \
                         (t <= t[i] + config.DISPLACEMENT_CHECK_WINDOW_S)
                latency_ms = (t[i] - target_onset_time) * 1000.0
                return SaccadeResult(
                    valid=True,
                    saccade_onset_time=float(t[i]),
                    latency_ms=float(latency_ms),
                    confidence=float(np.mean(conf[window])) if window.any()
                    else float(np.mean(conf)),
                    peak_velocity=peak_velocity,
                    threshold_used=threshold,
                    n_samples=int(t.size),
                    median_interval_ms=median_dt * 1000.0,
                    reason="ok",
                )
        i = j + 1

    return SaccadeResult(False, n_samples=int(t.size),
                         threshold_used=threshold,
                         peak_velocity=peak_velocity,
                         median_interval_ms=median_dt * 1000.0,
                         confidence=float(np.mean(conf)),
                         reason="no_valid_saccade")


def _direction_ok(t, x, y, onset_index, base_x, base_y, axis_x, axis_y):
    """
    The movement starting at onset_index must carry the pupil far enough
    along the instructed axis, and must not be dominated by off-axis motion.
    """
    window = np.where((t >= t[onset_index]) &
                      (t <= t[onset_index] + config.DISPLACEMENT_CHECK_WINDOW_S))[0]
    if window.size == 0:
        return False

    dx = x[window] - base_x
    dy = y[window] - base_y
    along = dx * axis_x + dy * axis_y                 # signed, target axis
    across = np.abs(dx * -axis_y + dy * axis_x)       # perpendicular magnitude

    k = int(np.argmax(along))
    if along[k] < config.MIN_DISPLACEMENT:
        return False                                   # too small or wrong way
    if across[k] > config.MAX_OFF_AXIS_RATIO * along[k]:
        return False                                   # mostly off-axis motion
    return True