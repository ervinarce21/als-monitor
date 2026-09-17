"""
Background eye-sampling thread.

Keeps the camera + pupil detection off the display thread so that target
presentation timing is not delayed by image processing.
"""

import threading
from collections import deque

from camera import CameraError, IRCamera
from pupil_tracker import PupilTracker


class EyeSampler:
    """Continuously produces timestamped PupilSample objects."""

    def __init__(self, buffer_seconds=10.0, expected_fps=120):
        self.camera = IRCamera()
        self.tracker = PupilTracker()
        maxlen = max(600, int(buffer_seconds * expected_fps))
        self._samples = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self.error = None            # last fatal capture error, if any
        self.frames_captured = 0
        self.frames_dropped = 0      # frames where detection failed
        self.latest_frame = None     # for the optional debug preview
        self.latest_sample = None

    # ------------------------------------------------------------------
    def start(self):
        self.camera.start()          # raises CameraError - handled by caller
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                timestamp, gray = self.camera.capture()
            except CameraError as exc:
                self.error = exc
                break
            except Exception as exc:               # unexpected, keep going once
                self.error = exc
                break

            sample = self.tracker.detect(gray, timestamp)
            self.frames_captured += 1
            if not sample.found:
                self.frames_dropped += 1

            with self._lock:
                self._samples.append(sample)
                self.latest_sample = sample
                self.latest_frame = gray

    # ------------------------------------------------------------------
    def get_samples(self, t_start, t_end):
        """All samples with t_start <= timestamp <= t_end (time-ordered)."""
        with self._lock:
            return [s for s in self._samples if t_start <= s.timestamp <= t_end]

    def get_recent(self, seconds, now):
        return self.get_samples(now - seconds, now)

    def clear(self):
        with self._lock:
            self._samples.clear()

    def get_latest_preview(self):
        """Return a consistent frame/sample snapshot for video feedback."""
        with self._lock:
            frame = None if self.latest_frame is None else self.latest_frame.copy()
            return frame, self.latest_sample

    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.camera.stop()
