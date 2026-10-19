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

from . import config


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
    """Noise-resistant pupil detector with short-term position continuity."""

    def __init__(self):
        k = max(3, int(config.MORPH_KERNEL) | 1)
        self._morph_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        self._blur = max(3, int(config.BLUR_KERNEL) | 1)
        self._scale = float(config.PROCESS_SCALE)
        self.last_debug = None    # (binary_image, roi_offset) for the preview
        self._last_position = None
        self._missed_frames = 0

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

    @staticmethod
    def _local_contrast(gray, contour, radius):
        """Return the brightness difference between a blob and its surround."""
        ring_radius = max(2, int(round(radius * 0.75)))
        x, y, width, height = cv2.boundingRect(contour)
        x0 = max(0, x - ring_radius)
        y0 = max(0, y - ring_radius)
        x1 = min(gray.shape[1], x + width + ring_radius)
        y1 = min(gray.shape[0], y + height + ring_radius)
        patch = gray[y0:y1, x0:x1]
        local_contour = contour - np.array([[[x0, y0]]], dtype=contour.dtype)
        mask = np.zeros(patch.shape, dtype=np.uint8)
        cv2.drawContours(mask, [local_contour], -1, 255, -1)

        ring_size = ring_radius * 2 + 1
        ring_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (ring_size, ring_size))
        expanded = cv2.dilate(mask, ring_kernel, iterations=1)
        ring = cv2.subtract(expanded, mask)
        if cv2.countNonZero(mask) == 0 or cv2.countNonZero(ring) == 0:
            return 0.0
        pupil_mean = cv2.mean(patch, mask=mask)[0]
        surround_mean = cv2.mean(patch, mask=ring)[0]
        return float(surround_mean - pupil_mean)

    def _not_found(self, timestamp):
        self._missed_frames += 1
        if self._missed_frames >= config.PUPIL_TRACKING_FORGET_FRAMES:
            self._last_position = None
        return PupilSample(timestamp, float("nan"), float("nan"), 0.0, False)

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
            return self._not_found(timestamp)

        best = None
        best_score = 0.0
        height, width = roi.shape[:2]
        border = max(0, int(round(config.PUPIL_BORDER_MARGIN_PX * self._scale)))
        max_jump = config.PUPIL_MAX_FRAME_JUMP_PX * self._scale
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

            x, y, box_w, box_h = cv2.boundingRect(contour)
            if (x <= border or y <= border or x + box_w >= width - border or
                    y + box_h >= height - border):
                continue

            if circularity < config.PUPIL_MIN_CIRCULARITY:
                continue
            if fill < config.PUPIL_MIN_FILL:
                continue

            if len(contour) >= 5:
                ellipse = cv2.fitEllipse(contour)
                (candidate_x, candidate_y), (axis_a, axis_b), _ = ellipse
                major_axis = max(axis_a, axis_b)
                aspect = min(axis_a, axis_b) / major_axis if major_axis > 0 else 0.0
            else:
                moments = cv2.moments(contour)
                if moments["m00"] == 0:
                    continue
                candidate_x = moments["m10"] / moments["m00"]
                candidate_y = moments["m01"] / moments["m00"]
                axis_a = axis_b = 2.0 * enclosing_r
                aspect = 1.0
            if aspect < config.PUPIL_MIN_ASPECT_RATIO:
                continue

            contrast = self._local_contrast(blurred, contour, enclosing_r)
            if contrast < config.PUPIL_MIN_CONTRAST:
                continue

            temporal_score = 0.5
            if self._last_position is not None:
                previous_x = (self._last_position[0] - off_x) * self._scale
                previous_y = (self._last_position[1] - off_y) * self._scale
                distance = math.hypot(candidate_x - previous_x,
                                      candidate_y - previous_y)
                if distance > max_jump:
                    continue
                temporal_score = max(0.0, 1.0 - distance / max_jump)

            shape_score = 0.5 * circularity + 0.5 * fill
            contrast_score = float(np.clip(
                contrast / config.PUPIL_GOOD_CONTRAST, 0.0, 1.0))
            score = (0.35 * shape_score + 0.35 * contrast_score +
                     0.15 * aspect + 0.15 * temporal_score)
            if score > best_score:
                best_score = score
                best = (candidate_x, candidate_y, axis_a, axis_b, enclosing_r)

        if best is None:
            return self._not_found(timestamp)

        cx, cy, axis_a, axis_b, enclosing_r = best
        radius = 0.25 * (axis_a + axis_b)

        # Back to full-frame coordinates.
        if self._scale != 1.0:
            cx /= self._scale
            cy /= self._scale
            radius /= self._scale
        cx += off_x
        cy += off_y

        confidence = float(np.clip(best_score, 0.0, 1.0))
        found = confidence >= config.PUPIL_MIN_CONFIDENCE
        if found:
            self._last_position = (float(cx), float(cy))
            self._missed_frames = 0
        else:
            self._missed_frames += 1
        return PupilSample(timestamp, float(cx), float(cy), confidence, found,
                           float(radius))
