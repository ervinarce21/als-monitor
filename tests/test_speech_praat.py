import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import parselmouth

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from als_monitor.speech_analysis.analysis import _pitch_hnr
from als_monitor.speech_analysis import config


class PraatTests(unittest.TestCase):
    def test_reference_agreement(self):
        rate = 48000
        t = np.arange(rate) / rate
        samples = 0.3 * np.sin(2 * np.pi * 180 * t)
        samples += np.random.default_rng(1).normal(0, 0.02, len(t))
        f0, hnr, frames, hnr_frames, metadata = _pitch_hnr(samples, rate)
        sound = parselmouth.Sound(samples, sampling_frequency=rate)
        reference = sound.to_harmonicity_cc(
            time_step=config.HNR_TIME_STEP, minimum_pitch=config.HNR_MIN_PITCH_HZ,
            silence_threshold=config.HNR_SILENCE_THRESHOLD,
            periods_per_window=config.HNR_PERIODS_PER_WINDOW).values.ravel()
        reference = reference[np.isfinite(reference) & (reference != -200)]
        self.assertAlmostEqual(hnr, float(reference.mean()), places=10)
        self.assertAlmostEqual(f0, 180, delta=2)
        self.assertGreater(frames, 0)
        self.assertEqual(hnr_frames, len(reference))
        self.assertEqual(metadata['engine'], 'praat-parselmouth')

    def test_silence_empty_short(self):
        for size in (0, 10, 48000):
            f0, hnr, frames, hnr_frames, _ = _pitch_hnr(np.zeros(size), 48000)
            self.assertIsNone(f0)
            self.assertIsNone(hnr)
            self.assertEqual(frames, 0)
            self.assertEqual(hnr_frames, 0)

    def test_dependency_error(self):
        with patch.dict(sys.modules, {'parselmouth': None}):
            with self.assertRaisesRegex(ValueError, 'pip install praat-parselmouth'):
                _pitch_hnr(np.zeros(100), 48000)


if __name__ == '__main__':
    unittest.main()
