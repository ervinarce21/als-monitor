import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from als_monitor.eye_tracker import config
from als_monitor.eye_tracker.saccade_detector import detect_saccade, direction_axis


def sample(timestamp, x, y):
    return SimpleNamespace(timestamp=timestamp, x=x, y=y,
                           confidence=1.0, found=True)


class WebcamSaccadeTests(unittest.TestCase):
    def test_front_facing_webcam_reverses_horizontal_image_direction(self):
        with patch.object(config, "CAMERA_BACKEND", "webcam"):
            self.assertEqual(direction_axis("right"), (-1, 0.0))
            self.assertEqual(direction_axis("left"), (1, 0.0))

    def test_30_fps_webcam_trace_is_not_rejected_as_slow(self):
        onset = 1.0
        samples = []
        for index in range(43):
            timestamp = index / 30.0
            x = 100.0
            if timestamp >= onset + 0.10:
                x -= min(4.0, (timestamp - onset - 0.10) * 80.0)
            samples.append(sample(timestamp, x, 100.0))

        with patch.object(config, "CAMERA_BACKEND", "webcam"):
            result = detect_saccade(samples, onset, "right")

        self.assertNotEqual(result.reason, "sampling_too_slow")


if __name__ == "__main__":
    unittest.main()
