"""
Background eye-sampling thread.

Keeps the camera + pupil detection off the display thread so that target
presentation timing is not delayed by image processing.
"""

import math
import os
import threading
from collections import deque

import cv2
import numpy as np

from . import config
from .camera import CameraError, create_camera
from .face_tracker import create_tracker


class EyeSampler:
    """Continuously produces timestamped PupilSample objects."""

    def __init__(self, buffer_seconds=10.0, expected_fps=120,
                 video_path=None):
        self.camera = create_camera()
        self.tracker = None
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
        self.video_path = video_path
        self._video_writer = None
        self._video_failed = False

    def _write_annotated_video(self, gray, sample):
        if not self.video_path or self._video_failed:
            return
        if self._video_writer is None:
            height, width = gray.shape[:2]
            os.makedirs(os.path.dirname(self.video_path) or ".", exist_ok=True)
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            self._video_writer = cv2.VideoWriter(
                self.video_path, fourcc, float(config.ANNOTATED_VIDEO_FPS),
                (width, height), True)
            if not self._video_writer.isOpened():
                print("[video] Could not create annotated eye video: %s" %
                      self.video_path, flush=True)
                self._video_writer.release()
                self._video_writer = None
                self._video_failed = True
                return
            print("[video] Saving annotated eye video: %s" % self.video_path,
                  flush=True)

        view = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR) if gray.ndim == 2 else gray.copy()
        found = (sample.found and not math.isnan(sample.x) and
                 not math.isnan(sample.y))
        if found:
            centre = (int(round(sample.x)), int(round(sample.y)))
            radius = max(4, int(round(sample.radius)))
            cv2.circle(view, centre, radius, (0, 255, 0), 2)
            cv2.drawMarker(view, centre, (0, 0, 255), cv2.MARKER_CROSS,
                           16, 1)
            status = "Pupil detected | confidence %.2f" % sample.confidence
            colour = (0, 255, 0)
        else:
            status = "Pupil not detected"
            colour = (0, 128, 255)
        cv2.rectangle(view, (0, 0), (view.shape[1], 54), (0, 0, 0), -1)
        cv2.putText(view, status, (10, 22), cv2.FONT_HERSHEY_SIMPLEX,
                    0.52, colour, 1, cv2.LINE_AA)
        cv2.putText(view, "t=%.6f" % sample.timestamp, (10, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1,
                    cv2.LINE_AA)
        self._video_writer.write(np.ascontiguousarray(view))

    # ------------------------------------------------------------------
    def start(self):
        self.tracker = create_tracker()
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

            try:
                sample = self.tracker.detect(gray, timestamp)
            except Exception as exc:
                self.error = exc
                break
            self.frames_captured += 1
            if not sample.found:
                self.frames_dropped += 1

            self._write_annotated_video(gray, sample)

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
            if not self._thread.is_alive():
                self._thread = None
        self.camera.stop()
        if self._video_writer is not None:
            self._video_writer.release()
            self._video_writer = None
            print("[video] Annotated eye video saved: %s" % self.video_path,
                  flush=True)
        if self.tracker is not None and (self._thread is None or not self._thread.is_alive()):
            close = getattr(self.tracker, "close", None)
            if close:
                close()
            self.tracker = None
