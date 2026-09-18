import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from als_monitor.eye_tracker import camera, config
from als_monitor.eye_tracker.face_tracker import FaceTracker, create_tracker
from als_monitor.eye_tracker.pupil_tracker import PupilTracker


class WebcamTests(unittest.TestCase):
    def test_csi_unchanged(self):
        with patch.object(config, 'CAMERA_BACKEND', 'csi'):
            self.assertIsInstance(camera.create_camera(), camera.IRCamera)
            self.assertIsInstance(create_tracker(), PupilTracker)

    def test_runtime_handoff(self):
        with patch.object(Path, 'is_file', return_value=True), \
                patch.object(camera.os, 'execv') as execute, \
                patch.object(config, 'CAMERA_BACKEND', 'csi'), \
                patch.object(config, 'WEBCAM_INDEX', 0):
            camera.configure_camera(['--camera', 'webcam'], 'als_monitor.eye_tracker.preview')
            self.assertIn('.venv-shoulder', execute.call_args.args[0])
            self.assertIn('als_monitor.eye_tracker.preview', execute.call_args.args[1])

    def test_capture_and_failures(self):
        cap = MagicMock()
        cap.get.return_value = 30
        cap.read.return_value = (True, np.zeros((4, 6, 3), dtype=np.uint8))
        with patch.object(cv2, 'VideoCapture', return_value=cap), patch.object(camera.time, 'sleep'):
            device = camera.WebcamCamera()
            device.start()
            timestamp, gray = device.capture()
            self.assertGreater(timestamp, 0)
            self.assertEqual(gray.shape, (4, 6))
            cap.read.return_value = (False, None)
            with self.assertRaises(camera.CameraError):
                device.capture()
            device.stop()
            cap.release.assert_called_once()
            cap.reset_mock()
            cap.isOpened.return_value = False
            with self.assertRaises(camera.CameraError):
                device.start()
            cap.release.assert_called_once()

    def test_landmarks_missing_and_blinks(self):
        tracker = FaceTracker.__new__(FaceTracker)
        tracker.mp = MagicMock()
        tracker.detector = MagicMock()
        tracker.last_timestamp = -1
        points = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]
        points[473] = SimpleNamespace(x=0.7, y=0.4)
        result = SimpleNamespace(face_landmarks=[points], face_blendshapes=[])
        tracker.detector.detect_for_video.return_value = result
        with patch.object(config, 'EYE', 'left'), patch.object(config, 'CAMERA_HFLIP', False), \
                patch.object(config, 'CAMERA_VFLIP', False):
            sample = tracker.detect(np.zeros((101, 101), dtype=np.uint8), 1.0)
            self.assertTrue(sample.found)
            self.assertAlmostEqual(sample.x, 70)
            tracker.detect(np.zeros((101, 101), dtype=np.uint8), 1.0)
            self.assertEqual(tracker.last_timestamp, 1001)
            result.face_blendshapes = [[SimpleNamespace(category_name='eyeBlinkLeft', score=0.9)]]
            self.assertFalse(tracker.detect(np.zeros((101, 101), dtype=np.uint8), 2).found)
            result.face_landmarks = []
            self.assertFalse(tracker.detect(np.zeros((101, 101), dtype=np.uint8), 3).found)
        tracker.close()
        tracker.detector.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
