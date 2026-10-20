"""Experimental iris image-coordinate tracking, not calibrated screen gaze."""

import os
from pathlib import Path

import cv2
import numpy as np

from . import config
from .pupil_tracker import PupilSample, PupilTracker


def create_tracker():
    # A USB-connected eye camera still supplies a close-up pupil image. Only
    # the full-face webcam mode uses MediaPipe iris landmarks.
    return FaceTracker() if config.CAMERA_BACKEND == "webcam" else PupilTracker()


def webcam_position_guidance(position):
    """Return frame-relative positioning guidance and whether it is acceptable."""
    if not position or not position.get("face_found"):
        return "Face not detected", False

    instructions = []
    width = position["width"]
    center_x = position["center_x"]
    center_y = position["center_y"]
    if width < config.WEBCAM_FACE_WIDTH_MIN:
        instructions.append("Move closer")
    elif width > config.WEBCAM_FACE_WIDTH_MAX:
        instructions.append("Move farther")
    if center_x < 0.5 - config.WEBCAM_FACE_CENTER_X_TOLERANCE:
        instructions.append("Move right in frame")
    elif center_x > 0.5 + config.WEBCAM_FACE_CENTER_X_TOLERANCE:
        instructions.append("Move left in frame")
    if center_y < 0.5 - config.WEBCAM_FACE_CENTER_Y_TOLERANCE:
        instructions.append("Move down in frame")
    elif center_y > 0.5 + config.WEBCAM_FACE_CENTER_Y_TOLERANCE:
        instructions.append("Move up in frame")
    return (" | ".join(instructions), False) if instructions else ("Position OK", True)


class FaceTracker:
    def __init__(self):
        model = Path(os.environ.get("NEXA_FACE_MODEL", str(
            Path(__file__).resolve().parents[3] / "data/models/face_landmarker.task")))
        if not model.is_file():
            raise RuntimeError("Face model missing: %s. Run scripts/setup-eye-webcam.sh "
                               "on the Pi; see README webcam setup." % model)
        import mediapipe as mp
        self.mp = mp
        self.detector = mp.tasks.vision.FaceLandmarker.create_from_options(
            mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_faces=1,
                output_face_blendshapes=True))
        self.last_timestamp = -1
        self.last_debug = None
        self.position_status = {"face_found": False}

    def detect(self, gray, timestamp):
        # Undo display flips so the model's anatomical eye indices stay correct.
        frame = gray
        if config.CAMERA_HFLIP:
            frame = cv2.flip(frame, 1)
        if config.CAMERA_VFLIP:
            frame = cv2.flip(frame, 0)
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                              data=cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB))
        self.last_timestamp = max(self.last_timestamp + 1, int(timestamp * 1000))
        result = self.detector.detect_for_video(image, self.last_timestamp)
        missing = PupilSample(timestamp, float("nan"), float("nan"), 0.0, False)
        if not result.face_landmarks or len(result.face_landmarks[0]) < 478:
            self.position_status = {"face_found": False}
            return missing
        left = config.EYE == "left"
        blink_name = "eyeBlinkLeft" if left else "eyeBlinkRight"
        if result.face_blendshapes:
            if any(item.category_name == blink_name and item.score >= 0.5
                   for item in result.face_blendshapes[0]):
                return missing
        landmarks = result.face_landmarks[0]
        face_points = np.array([(point.x, point.y) for point in landmarks])
        if not np.isfinite(face_points).all():
            self.position_status = {"face_found": False}
            return missing
        face_points = np.clip(face_points, 0.0, 1.0)
        min_x, min_y = np.min(face_points, axis=0)
        max_x, max_y = np.max(face_points, axis=0)
        center_x = float((min_x + max_x) / 2.0)
        center_y = float((min_y + max_y) / 2.0)
        if config.CAMERA_HFLIP:
            center_x = 1.0 - center_x
            min_x, max_x = 1.0 - max_x, 1.0 - min_x
        if config.CAMERA_VFLIP:
            center_y = 1.0 - center_y
            min_y, max_y = 1.0 - max_y, 1.0 - min_y
        self.position_status = {
            "face_found": True,
            "left": float(min_x), "top": float(min_y),
            "right": float(max_x), "bottom": float(max_y),
            "center_x": center_x, "center_y": center_y,
            "width": float(max_x - min_x),
        }
        center_index = 473 if left else 468
        indices = [center_index] + list(range(center_index + 1, center_index + 5))
        points = np.array([(landmarks[i].x, landmarks[i].y) for i in indices])
        if not np.isfinite(points).all() or (points < 0).any() or (points > 1).any():
            return missing
        height, width = gray.shape
        pixels = points * [width - 1, height - 1]
        x, y = pixels[0]
        radius = float(np.mean(np.linalg.norm(pixels[1:] - pixels[0], axis=1)))
        if config.CAMERA_HFLIP:
            x = width - 1 - x
        if config.CAMERA_VFLIP:
            y = height - 1 - y
        # Face Landmarker supplies no per-iris confidence: 1 means accepted,
        # not a calibrated probability. Sampling-quality gates remain unchanged.
        return PupilSample(timestamp, float(x), float(y), 1.0, True, radius)

    def close(self):
        self.detector.close()
