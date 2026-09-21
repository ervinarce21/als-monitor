"""PCM WAV timing measurements and Praat F0/HNR via Parselmouth."""

import math
import wave

import numpy as np

from . import config


def load_wav(path):
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if sample_width != 2:
        raise ValueError("Only 16-bit PCM WAV files are supported")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, sample_rate


def _frames(samples, size):
    if len(samples) < size:
        return np.empty((0, size))
    count = len(samples) // size
    return samples[:count * size].reshape(count, size)


def _speech_timing(samples, sample_rate):
    frame_size = max(1, int(sample_rate * config.VAD_FRAME_DURATION_MS / 1000))
    frames = _frames(samples, frame_size)
    if not len(frames):
        return 0.0, 0.0, 0, np.zeros(0, dtype=bool)
    rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    absolute_floor = 10 ** (config.QC_MIN_RMS_DBFS / 20)
    noise_based_threshold = float(np.percentile(rms, 20)) * 2.5
    # In a sustained-vowel recording the 20th percentile is speech, not
    # background noise. Cap the adaptive threshold below normal signal energy
    # so an evenly voiced recording is not incorrectly treated as silence.
    signal_cap = float(np.percentile(rms, 80)) * 0.5
    threshold = max(absolute_floor, min(noise_based_threshold, signal_cap))
    voiced = rms >= threshold
    frame_seconds = frame_size / sample_rate
    min_speech = max(1, round(config.MIN_SPEECH_SEGMENT_SECONDS / frame_seconds))
    min_pause = max(1, round(config.MIN_PAUSE_DURATION_SECONDS / frame_seconds))

    # Remove isolated short speech bursts.
    start = 0
    while start < len(voiced):
        end = start + 1
        while end < len(voiced) and voiced[end] == voiced[start]:
            end += 1
        if voiced[start] and end - start < min_speech:
            voiced[start:end] = False
        start = end

    speech_seconds = float(np.count_nonzero(voiced) * frame_seconds)
    pause_seconds = 0.0
    pause_count = 0
    indices = np.where(voiced)[0]
    if indices.size:
        region = voiced[indices[0]:indices[-1] + 1]
        start = 0
        while start < len(region):
            end = start + 1
            while end < len(region) and region[end] == region[start]:
                end += 1
            if not region[start] and end - start >= min_pause:
                pause_count += 1
                pause_seconds += (end - start) * frame_seconds
            start = end
    return speech_seconds, pause_seconds, pause_count, voiced


def _pitch_hnr(samples, sample_rate):
    try:
        import parselmouth
    except ImportError as exc:
        raise ValueError("Praat analysis requires praat-parselmouth. Install it with "
                         "python -m pip install praat-parselmouth in the speech environment.") from exc
    metadata = {
        "engine": "praat-parselmouth",
        "parselmouth_version": parselmouth.__version__,
        "praat_version": parselmouth.PRAAT_VERSION,
        "pitch_method": "raw_autocorrelation",
        "pitch_floor_hz": config.F0_PITCH_FLOOR_HZ,
        "pitch_ceiling_hz": config.F0_PITCH_CEILING_HZ,
        "pitch_time_step": config.F0_TIME_STEP,
        "hnr_method": "cross_correlation",
        "hnr_time_step": config.HNR_TIME_STEP,
        "hnr_min_pitch_hz": config.HNR_MIN_PITCH_HZ,
        "hnr_silence_threshold": config.HNR_SILENCE_THRESHOLD,
        "hnr_periods_per_window": config.HNR_PERIODS_PER_WINDOW,
        "aggregation": "arithmetic_mean_of_valid_frames",
        "segment": "whole_recording",
        "channels": "averaged_to_mono",
    }
    pitches = np.array([])
    hnrs = np.array([])
    if len(samples):
        sound = parselmouth.Sound(samples, sampling_frequency=sample_rate)
        # Do not pad short inputs or apply the separate RMS timing mask to Praat.
        if sound.duration >= 3.0 / config.F0_PITCH_FLOOR_HZ:
            pitch = sound.to_pitch_ac(
                time_step=config.F0_TIME_STEP or None,
                pitch_floor=config.F0_PITCH_FLOOR_HZ,
                pitch_ceiling=config.F0_PITCH_CEILING_HZ)
            pitches = pitch.selected_array["frequency"]
        if sound.duration >= (1.0 + config.HNR_PERIODS_PER_WINDOW) / config.HNR_MIN_PITCH_HZ:
            harmonicity = sound.to_harmonicity_cc(
                time_step=config.HNR_TIME_STEP,
                minimum_pitch=config.HNR_MIN_PITCH_HZ,
                silence_threshold=config.HNR_SILENCE_THRESHOLD,
                periods_per_window=config.HNR_PERIODS_PER_WINDOW)
            hnrs = harmonicity.values.ravel()
    valid_pitch = pitches[np.isfinite(pitches) & (pitches > 0)]
    # Praat's -200 sentinel means undefined; real negative HNR is retained.
    valid_hnr = hnrs[np.isfinite(hnrs) & (hnrs != -200)]
    return (_mean_or_none(valid_pitch), _mean_or_none(valid_hnr), len(valid_pitch),
            len(valid_hnr), metadata)


def _mean_or_none(values):
    return float(np.mean(values)) if len(values) else None


def analyze_wav(path, task):
    samples, sample_rate = load_wav(path)
    duration = len(samples) / sample_rate if sample_rate else 0.0
    rms = float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0.0
    rms_dbfs = 20.0 * math.log10(max(rms, 1e-12))
    clipping = float(np.mean(np.abs(samples) >= 0.999)) if len(samples) else 0.0
    speech, pauses, pause_count, voiced = _speech_timing(samples, sample_rate)
    mean_f0, hnr, voiced_frames, hnr_frames, parameters = _pitch_hnr(samples, sample_rate)

    flags = []
    if duration < config.QC_MIN_DURATION_SECONDS:
        flags.append(config.QF_TOO_SHORT)
    if rms_dbfs < config.QC_MIN_RMS_DBFS:
        flags.append(config.QF_TOO_QUIET)
    if clipping > config.QC_CLIPPING_SAMPLE_FRACTION:
        flags.append(config.QF_CLIPPING_DETECTED)
    if speech < config.QC_MIN_SPEECH_DURATION_SECONDS:
        flags.append(config.QF_INSUFFICIENT_SPEECH)
    if mean_f0 is None:
        flags.append(config.QF_INVALID_F0)
    if hnr is None:
        flags.append(config.QF_INVALID_HNR)
    quality = config.QUALITY_VALID if not flags else config.QUALITY_WARNING

    return {
        "task": task,
        "sample_rate_hz": sample_rate,
        "recording_duration_sec": duration,
        "speech_duration_sec": speech,
        "pause_duration_sec": pauses,
        "num_pauses": pause_count,
        "pause_percentage": (100.0 * pauses / duration) if duration else None,
        "mean_f0_hz": mean_f0,
        "hnr_db": hnr,
        "rms_dbfs": rms_dbfs,
        "clipping_fraction": clipping,
        "voiced_frames": voiced_frames,
        "hnr_valid_frames": hnr_frames,
        "analysis_parameters": parameters,
        "software_version": config.NEXA_SPEECH_MODULE_VERSION,
        "quality_status": quality,
        "quality_flags": flags,
    }
