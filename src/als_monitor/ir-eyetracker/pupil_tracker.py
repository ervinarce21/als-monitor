"""
Lightweight IR pupil detection.

Pipeline: ROI -> optional downscale -> blur -> dark threshold -> morphology
-> contours -> shape scoring -> ellipse fit.

No neural networks; this runs comfortably in real time on a Pi 4.
"""

import math
from dataclasses import dataclass

import cv2
import numpy as np

import config


@dataclass
class PupilSample:
    timestamp: float          # perf_counter seconds
    x: float                  # full-frame image coordinates, pixels
    y: float
    confidence: float         # 0..1
    found: bool
    radius: float = 0.0


NO_PUPIL = PupilSample(0.0, float("nan"), float("nan"), 0.0, False)


class PupilTracker:
    """Stateless per-frame detector (kept as a class to cache kernels)."""

    def __init__(self):
        k = max(3, int(config.MORPH_KERNEL) | 1)
        self._morph_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        self._blur = max(3, int(config.BLUR_KERNEL) | 1)
        self._scale = float(config.PROCESS_SCALE)
        self.last_debug = None    # (binary_image, roi_offset) for the preview

    # ------------------------------------------------------------------
    def _roi(self, gray):
        """Return (roi_image, x_offset, y_offset)."""
        if config.EYE_ROI_MODE != "half":
            return gray, 0, 0
        h, w = gray.shape[:2]
        half = w // 2
        # Image left half == participant's right eye in a non-mirrored view.
        if config.EYE == "left":
            return gray[:, half:], half, 0
        return gray[:, :half], 0, 0

    def _threshold_value(self, img):
        if config.PUPIL_THRESHOLD_MODE == "fixed":
            value = float(config.PUPIL_THRESHOLD)
        else:
            value = float(np.percentile(img, config.PUPIL_DARK_PERCENTILE))
            value += config.PUPIL_THRESHOLD_OFFSET
        return int(np.clip(value, config.PUPIL_THRESHOLD_MIN,
                           config.PUPIL_THRESHOLD_MAX))

    # ------------------------------------------------------------------
    def detect(self, gray, timestamp):
        """
        Detect the pupil in one grayscale frame.

        Never raises: an undetected pupil returns found=False.
        """
        try:
            return self._detect(gray, timestamp)
        except Exception:
            return PupilSample(timestamp, float("nan"), float("nan"), 0.0, False)

    def _detect(self, gray, timestamp):
        roi, off_x, off_y = self._roi(gray)

        if self._scale != 1.0:
            roi = cv2.resize(roi, None, fx=self._scale, fy=self._scale,
                             interpolation=cv2.INTER_AREA)

        blurred = cv2.GaussianBlur(roi, (self._blur, self._blur), 0)
        thr = self._threshold_value(blurred)
        _, binary = cv2.threshold(blurred, thr, 255, cv2.THRESH_BINARY_INV)

        if config.MORPH_OPEN_ITER:
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, self._morph_kernel,
                                      iterations=config.MORPH_OPEN_ITER)
        if config.MORPH_CLOSE_ITER:
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, self._morph_kernel,
                                      iterations=config.MORPH_CLOSE_ITER)

        if config.DEBUG_PREVIEW:
            self.last_debug = binary

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return PupilSample(timestamp, float("nan"), float("nan"), 0.0, False)

        best = None
        best_score = 0.0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < config.PUPIL_MIN_AREA or area > config.PUPIL_MAX_AREA:
                continue
            perimeter = cv2.arcLength(contour, True)
            if perimeter <= 0:
                continue

            circularity = 4.0 * math.pi * area / (perimeter * perimeter)
            circularity = min(circularity, 1.0)
            (_, _), enclosing_r = cv2.minEnclosingCircle(contour)
            if enclosing_r <= 0:
                continue
            fill = area / (math.pi * enclosing_r * enclosing_r)

            if circularity < config.PUPIL_MIN_CIRCULARITY:
                continue
            if fill < config.PUPIL_MIN_FILL:
                continue

            # Confidence: shape quality only. Area is not rewarded, otherwise
            # a large dark eyelid shadow would outrank the real pupil.
            score = 0.6 * circularity + 0.4 * fill
            if score > best_score:
                best_score = score
                best = (contour, enclosing_r)

        if best is None:
            return PupilSample(timestamp, float("nan"), float("nan"), 0.0, False)

        contour, enclosing_r = best
        if len(contour) >= 5:
            (cx, cy), (ax1, ax2), _ = cv2.fitEllipse(contour)
            radius = 0.25 * (ax1 + ax2)
        else:
            moments = cv2.moments(contour)
            if moments["m00"] == 0:
                return PupilSample(timestamp, float("nan"), float("nan"),
                                   0.0, False)
            cx = moments["m10"] / moments["m00"]
            cy = moments["m01"] / moments["m00"]
            radius = enclosing_r

        # Back to full-frame coordinates.
        if self._scale != 1.0:
            cx /= self._scale
            cy /= self._scale
            radius /= self._scale
        cx += off_x
        cy += off_y

        confidence = float(np.clip(best_score, 0.0, 1.0))
        found = confidence >= config.PUPIL_MIN_CONFIDENCE
        return PupilSample(timestamp, float(cx), float(cy), confidence, found,
                           float(radius))