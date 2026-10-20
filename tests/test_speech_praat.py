import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import parselmouth

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from als_monitor.speech_analysis.analysis import (
    _pitch_hnr, _speech_timing, _speech_timing_rms_fallback,
)
from als_monitor.speech_analysis import config


class PraatTests(unittest.TestCase):
    def test_short_rms_fallback_has_numeric_span(self):
        speech, pauses, count, span = _speech_timing_rms_fallback(
            np.zeros(10), 48000)
        self.assertEqual((speech, pauses, count, span), (0.0, 0.0, 0, 0.0))

    def test_praat_like_fallback_merges_short_silence(self):
        rate = 48000
        tone_time = np.arange(rate) / rate
        tone = 0.3 * np.sin(2 * np.pi * 180 * tone_time)
        short_gap = np.zeros(int(rate * 0.2))
        speech, pauses, count, span = _speech_timing_rms_fallback(
            np.concatenate([tone, short_gap, tone]), rate)
        self.assertEqual(count, 0)
        self.assertEqual(pauses, 0.0)
        self.assertGreater(speech, 2.0)
        self.assertAlmostEqual(span, speech, places=6)

    def test_praat_like_fallback_keeps_long_pause(self):
        rate = 48000
        tone_time = np.arange(rate) / rate
        tone = 0.3 * np.sin(2 * np.pi * 180 * tone_time)
        long_gap = np.zeros(int(rate * 0.5))
        speech, pauses, count, span = _speech_timing_rms_fallback(
            np.concatenate([tone, long_gap, tone]), rate)
        self.assertEqual(count, 1)
        self.assertAlmostEqual(pauses, 0.5, delta=0.08)
        self.assertAlmostEqual(span, speech + pauses, places=6)

    def test_praat_pause_segmentation(self):
        rate = 48000
        tone_time = np.arange(rate) / rate
        tone = 0.3 * np.sin(2 * np.pi * 180 * tone_time)
        samples = np.concatenate([tone, np.zeros(rate // 2), tone])
        speech, pauses, count, span, metadata = _speech_timing(samples, rate)
        self.assertEqual(metadata['method'],
                         'praat_sound_to_textgrid_silences')
        self.assertEqual(metadata['status'], 'ok')
        self.assertEqual(count, 1)
        self.assertAlmostEqual(pauses, 0.5, delta=0.1)
        self.assertAlmostEqual(span, speech + pauses, places=6)

    def test_reference_agreement(self):
        rate = 48000
        t = np.arange(rate) / rate
        samples = 0.3 * np.sin(2 * np.pi * 180 * t)
        samples += np.random.default_rng(1).normal(0, 0.02, len(t))
        f0, hnr, frames, hnr_frames, metadata = _pitch_hnr(samples, rate)
        sound = parselmouth.Sound(samples, sampling_frequency=rate)
        reference_pitch = sound.to_pitch_ac(
            time_step=config.F0_TIME_STEP or None,
            pitch_floor=config.F0_PITCH_FLOOR_HZ,
            max_number_of_candidates=config.F0_MAX_NUMBER_OF_CANDIDATES,
            very_accurate=config.F0_VERY_ACCURATE,
            silence_threshold=config.F0_SILENCE_THRESHOLD,
            voicing_threshold=config.F0_VOICING_THRESHOLD,
            octave_cost=config.F0_OCTAVE_COST,
            octave_jump_cost=config.F0_OCTAVE_JUMP_COST,
            voiced_unvoiced_cost=config.F0_VOICED_UNVOICED_COST,
            pitch_ceiling=config.F0_PITCH_CEILING_HZ,
        ).selected_array["frequency"]
        reference_pitch = reference_pitch[
            np.isfinite(reference_pitch) & (reference_pitch > 0)]
        reference = sound.to_harmonicity_cc(
            time_step=config.HNR_TIME_STEP, minimum_pitch=config.HNR_MIN_PITCH_HZ,
            silence_threshold=config.HNR_SILENCE_THRESHOLD,
            periods_per_window=config.HNR_PERIODS_PER_WINDOW).values.ravel()
        reference = reference[np.isfinite(reference) & (reference != -200)]
        self.assertAlmostEqual(f0, float(reference_pitch.mean()), places=10)
        self.assertAlmostEqual(hnr, float(reference.mean()), places=10)
        self.assertAlmostEqual(f0, 180, delta=2)
        self.assertGreater(frames, 0)
        self.assertEqual(hnr_frames, len(reference))
        self.assertEqual(metadata['engine'], 'praat-parselmouth')
        self.assertEqual(metadata['pitch_method'], 'raw_autocorrelation')
        self.assertAlmostEqual(
            metadata['pitch_effective_time_step_sec'],
            0.75 / config.F0_PITCH_FLOOR_HZ)
        self.assertEqual(metadata['pitch_max_number_of_candidates'], 15)
        self.assertGreater(metadata['pitch_valid_frame_percent'], 0)
        self.assertGreater(metadata['hnr_valid_frame_percent'], 0)

    def test_silence_empty_short(self):
        for size in (0, 10, 48000):
            f0, hnr, frames, hnr_frames, _ = _pitch_hnr(np.zeros(size), 48000)
            self.assertIsNone(f0)
            self.assertIsNone(hnr)
            self.assertEqual(frames, 0)
            self.assertEqual(hnr_frames, 0)

    def test_dependency_error(self):
        with patch.dict(sys.modules, {'parselmouth': None}):
            f0, hnr, frames, hnr_frames, metadata = _pitch_hnr(
                np.zeros(100), 48000)
            self.assertIsNone(f0)
            self.assertIsNone(hnr)
            self.assertEqual(frames, 0)
            self.assertEqual(hnr_frames, 0)
            self.assertEqual(metadata['engine_status'], 'unavailable')
            self.assertIn('praat-parselmouth', metadata['install_hint'])


if __name__ == '__main__':
    unittest.main()
