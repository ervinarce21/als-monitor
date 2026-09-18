"""Anatomical left/right landmarks from unmirrored webcam frames."""

import os
from pathlib import Path

import cv2


class ShoulderPose:
    def __init__(self):
        import mediapipe as mp
        self.mp = mp
        model = Path(os.environ.get("NEXA_POSE_MODEL", str(
            Path(__file__).resolve().parents[3] / "data" /
            "models" / "pose_landmarker_lite.task")))
        if not model.is_file():
            raise RuntimeError("Pose model missing: %s. See README shoulder pose setup." % model)
        self.detector = mp.tasks.vision.PoseLandmarker.create_from_options(
            mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=1))
        self.last_timestamp = -1

    def detect(self, frame, timestamp):
        timestamp = max(self.last_timestamp + 1, int(timestamp * 1000))
        self.last_timestamp = timestamp
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                              data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        result = self.detector.detect_for_video(image, timestamp)
        points = {}
        if result.pose_landmarks:
            height, width = frame.shape[:2]
            for name, index in (("LEFT_SHOULDER", 11), ("RIGHT_SHOULDER", 12),
                                ("LEFT_WRIST", 15), ("RIGHT_WRIST", 16)):
                point = result.pose_landmarks[0][index]
                if (point.visibility >= 0.6 and point.presence >= 0.6
                        and 0 <= point.x <= 1 and 0 <= point.y <= 1):
                    points[name] = (min(width - 1, int(point.x * width)),
                                    min(height - 1, int(point.y * height)))
        return points

    def close(self):
        self.detector.close()
