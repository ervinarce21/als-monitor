# Speech Analysis with Praat

This document describes how the NEXA speech assessment uses Praat through the
Python package `praat-parselmouth`. It records the implemented methods and
parameters so results can be reviewed and reproduced.

NEXA is a research measurement prototype. These settings are explicit analysis
choices, not diagnostic criteria or universal clinical standards.

## Implementation Files

- `src/als_monitor/speech_analysis/analysis.py`: WAV loading, pause analysis,
  F0, HNR, and quality metrics.
- `src/als_monitor/speech_analysis/config.py`: configurable analysis settings.
- `src/als_monitor/speech_analysis/main.py`: recording, analysis dispatch,
  database storage, and JSON output.
- `src/als_monitor/speech_analysis/schema.sql`: speech database schema.
- `tests/test_speech_praat.py`: reference and segmentation tests.

The current measurement-affecting software version is:

```text
0.3.0-praat-pauses
```

## Package Requirement

The distribution is named `praat-parselmouth`, but Python imports it as
`parselmouth`:

```bash
python3 -m pip install praat-parselmouth
python3 -c "import parselmouth; print(parselmouth.__version__, parselmouth.PRAAT_VERSION)"
```

Do not install the unrelated package named only `parselmouth`. A correct
installation provides `parselmouth.Sound`, `parselmouth.praat`, and an embedded
Praat version.

On Raspberry Pi, run the checks with the same interpreter used by NEXA:

```bash
cd "$HOME/Documents/ALS Monitor/als-monitor"
.venv/bin/python -c "import parselmouth; print(parselmouth.__version__, parselmouth.PRAAT_VERSION)"
```

## Input Audio

Recorded assessments use:

| Property | Setting |
|---|---|
| Container | WAV |
| Encoding | Signed 16-bit PCM |
| Channels | Mono |
| Preferred sample rate | 48,000 Hz |
| Sample-rate fallback | Selected microphone's default rate |

Existing WAV analysis accepts 16-bit PCM. Multichannel input is averaged to
mono before analysis. Samples are converted to floating-point values in the
range represented by signed PCM16.

Pausing a NEXA recording excludes the paused samples from the WAV. The recorded
pause duration in `paused_duration_sec` is therefore an operator interruption,
not a detected within-speech pause.

## Which Measurements Use Praat

Praat is used for:

1. Intensity-based sounding/silence segmentation and internal pauses.
2. Fundamental frequency, or F0.
3. Harmonic-to-noise ratio, or HNR.

NEXA itself computes:

- Recording duration from WAV frames and sample rate.
- RMS level in dBFS.
- Clipping fraction.
- Summary aggregation and quality flags.
- Early-finish and operator-pause metadata.
- Database and JSON storage.

## Pause Analysis

### Praat operation

NEXA calls Praat's:

```text
Sound: To TextGrid (silences)
```

Praat bandpass-filters the sound from 80 to 8000 Hz, calculates an intensity
contour, and labels silent and sounding intervals. Its silence threshold is
relative to the maximum intensity in the recording, not an absolute dBFS level.

Implemented settings:

| Parameter | NEXA setting |
|---|---:|
| Silence threshold | -25 dB relative to maximum |
| Minimum silent interval | 0.300 s |
| Minimum sounding interval | 0.100 s |
| Silent label | `silent` |
| Sounding label | `sounding` |

The `0.300 s` threshold means a silent interval shorter than 300 ms is not
reported as a pause. This helps avoid counting brief consonant closures and
other small gaps. It is a study parameter and must be validated for the
intended population and protocol.

Official references:

- [Praat: Sound to TextGrid (silences)](https://www.fon.hum.uva.nl/praat/manual/Sound__To_TextGrid__silences____.html)
- [Praat: Intensity to TextGrid (silences)](https://www.fon.hum.uva.nl/praat/manual/Intensity__To_TextGrid__silences____.html)

### Counted interval

NEXA finds the first and last Praat `sounding` intervals. It excludes silence
before the first sounding interval and after the last sounding interval.

Within that analyzed span:

```text
speech_duration_sec = sum of sounding intervals
pause_duration_sec  = sum of internal silent intervals
num_pauses          = number of internal silent intervals
analyzed_span_sec   = speech_duration_sec + pause_duration_sec
pause_percentage    = 100 * pause_duration_sec / analyzed_span_sec
```

The denominator is not the fixed recording duration. This prevents setup time,
early completion, and trailing silence from inflating or distorting the
within-task pause percentage.

### Praat-unavailable fallback

If Praat cannot load or its silence command fails, NEXA preserves the WAV and
uses the older frame-RMS segmentation as a fallback. The run is marked with:

```text
quality_flags: ["VAD_FAILURE", ...]
analysis_parameters.speech_timing.method: "rms_energy_fallback"
```

Fallback pause values must not be treated as equivalent to Praat-segmented
values.

## Fundamental Frequency

NEXA creates a `parselmouth.Sound` from the complete mono signal and calls raw
autocorrelation pitch analysis through `Sound.to_pitch_ac`.

| Parameter | NEXA setting |
|---|---:|
| Method | Raw autocorrelation |
| Pitch floor | 75 Hz |
| Pitch ceiling | 500 Hz |
| Time step | Praat automatic |
| Segment | Whole recording |
| Aggregation | Arithmetic mean of valid frequency frames |

Zero, nonfinite, and unvoiced pitch frames are excluded. If no valid frames
remain, `mean_f0_hz` is `null` and `INVALID_F0` is added to the quality flags.

The whole recording is analyzed; NEXA does not currently trim to the Praat
sounding intervals before calculating F0.

Official reference:

- [Praat pitch-analysis guidance](https://www.fon.hum.uva.nl/praat/manual/how_to_choose_a_pitch_analysis_method.html)

## Harmonic-to-Noise Ratio

NEXA calls Praat cross-correlation harmonicity through
`Sound.to_harmonicity_cc`.

| Parameter | NEXA setting |
|---|---:|
| Method | Cross-correlation harmonicity |
| Time step | 0.01 s |
| Minimum pitch | 75 Hz |
| Silence threshold | 0.1 relative amplitude criterion |
| Periods per window | 1.0 |
| Segment | Whole recording |
| Aggregation | Arithmetic mean of valid HNR frames |

Praat's `-200` undefined sentinel and nonfinite values are excluded. Genuine
negative HNR values are retained because HNR is a logarithmic ratio and must
not be converted to an absolute value. If no valid values remain, `hnr_db` is
`null` and `INVALID_HNR` is added to the quality flags.

The HNR silence threshold is separate from the pause detector's `-25 dB`
relative intensity threshold. They have different units and purposes.

Official reference:

- [Praat: Sound to Harmonicity](https://www.fon.hum.uva.nl/praat/manual/Sound__To_Harmonicity__ac____.html)

## Other Quality Checks

The current checks include:

| Check | Current condition |
|---|---|
| Too short | Recording below 1.0 s |
| Too quiet | RMS below -45 dBFS |
| Clipping | At least 0.001 of samples near full scale |
| Insufficient speech | Detected speech below 1.0 s |
| Invalid F0 | No valid pitch result |
| Invalid HNR | No valid harmonicity result |
| VAD failure | Praat pause segmentation unavailable |

Any implemented flag changes `quality_status` from `VALID` to `WARNING`.
`VALID` means no implemented warning fired; it is not a clinical validity
classification.

## Output Fields

The primary output is `speech_summary.json`. Relevant fields include:

```json
{
  "task": "connected_speech",
  "sample_rate_hz": 48000,
  "recording_duration_sec": 30.0,
  "speech_duration_sec": 22.4,
  "pause_duration_sec": 4.1,
  "num_pauses": 6,
  "pause_percentage": 15.5,
  "pause_percentage_denominator_sec": 26.5,
  "mean_f0_hz": 155.2,
  "hnr_db": 12.4,
  "rms_dbfs": -27.0,
  "clipping_fraction": 0.0,
  "ended_early": false,
  "paused_duration_sec": 0.0,
  "quality_status": "VALID",
  "quality_flags": [],
  "software_version": "0.3.0-praat-pauses"
}
```

Values above are illustrative, not reference ranges.

`analysis_parameters` records the actual method, thresholds, installed
Parselmouth version, and embedded Praat version. Preserve this object when
exporting data.

## Reproducibility and Comparability

Do not combine measurements merely because their JSON field names match.
Confirm the following before longitudinal comparison:

- Same speech task and instructions.
- Same microphone, position, gain, and room conditions.
- Same WAV format and sample-rate policy.
- Same NEXA software version.
- Same embedded Praat and Parselmouth versions.
- Same pause, F0, and HNR parameters.
- Same early-finish and operator-pause policy.
- No `rms_energy_fallback` runs mixed with Praat pause results.

Pause results produced before `0.3.0-praat-pauses` used a custom RMS classifier,
a different minimum gap, and a different percentage denominator. Reanalyze the
original WAV files with the current version before comparing old and new pause
measurements.

## Verification

Run the automated reference tests in the same environment used for analysis:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests/test_speech_praat.py -v
```

The tests cover:

- F0 and HNR agreement with direct Parselmouth calls.
- Empty, silent, and short recordings.
- Praat dependency fallback behavior.
- A synthetic tone-silence-tone pause segmentation case.

For an installed environment, verify package identity directly:

```bash
.venv/bin/python -c "import parselmouth; from parselmouth import praat; print(parselmouth.__version__, parselmouth.PRAAT_VERSION)"
```

For a real assessment, inspect:

```text
speech_summary.json
  software_version
  quality_status
  quality_flags
  analysis_parameters.engine_status
  analysis_parameters.speech_timing.method
  analysis_parameters.speech_timing.status
```

Listen to the saved WAV and manually inspect a representative set of detected
pause boundaries in Praat before accepting the thresholds for a study. Quiet
speech, changing microphone distance, background noise, reverberation, and
automatic microphone gain can all alter intensity-based segmentation.

## Known Limitations

- A relative threshold can behave differently when one unusually loud sound
  establishes the recording maximum.
- Whole-recording F0 and HNR can include silence and non-target vocalizations.
- No calibrated sound-pressure level is measured.
- The pause detector does not determine whether silence is linguistic,
  respiratory, technical, or caused by task interruption.
- Operator-paused time is excluded from the WAV and cannot be recovered from
  acoustic analysis.
- Current threshold choices require validation for the intended ALS cohort,
  language, task, microphone, and room.

