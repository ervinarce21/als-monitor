"""Dependency-light acoustic measurements for PCM WAV recordings."""

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
    threshold = max(10 ** (config.QC_MIN_RMS_DBFS / 20),
                    float(np.percentile(rms, 20)) * 2.5)
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
    frame_size = max(256, int(sample_rate * 0.04))
    hop = max(1, frame_size // 2)
    min_lag = max(1, int(sample_rate / config.F0_PITCH_CEILING_HZ))
    max_lag = min(frame_size - 1, int(sample_rate / config.F0_PITCH_FLOOR_HZ))
    pitches = []
    hnrs = []
    for offset in range(0, max(0, len(samples) - frame_size + 1), hop):
        frame = samples[offset:offset + frame_size]
        frame = frame - np.mean(frame)
        energy = float(np.dot(frame, frame))
        if energy < 1e-6:
            continue
        corr = np.correlate(frame, frame, mode="full")[frame_size - 1:]
        corr /= max(corr[0], 1e-12)
        section = corr[min_lag:max_lag + 1]
        lag = min_lag + int(np.argmax(section))
        strength = float(corr[lag])
        if strength < 0.3:
            continue
        pitches.append(sample_rate / lag)
        hnrs.append(10.0 * math.log10(max(strength, 1e-6) /
                                      max(1.0 - strength, 1e-6)))
    return (_mean_or_none(pitches), _mean_or_none(hnrs), len(pitches))


def _mean_or_none(values):
    return float(np.mean(values)) if values else None


def analyze_wav(path, task):
    samples, sample_rate = load_wav(path)
    duration = len(samples) / sample_rate if sample_rate else 0.0
    rms = float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0.0
    rms_dbfs = 20.0 * math.log10(max(rms, 1e-12))
    clipping = float(np.mean(np.abs(samples) >= 0.999)) if len(samples) else 0.0
    speech, pauses, pause_count, _ = _speech_timing(samples, sample_rate)
    mean_f0, hnr, voiced_frames = _pitch_hnr(samples, sample_rate)

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
        "quality_status": quality,
        "quality_flags": flags,
    }

