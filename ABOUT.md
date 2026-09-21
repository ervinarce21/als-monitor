# NEXA / ALS Monitor

Program Overview and Operator Guide

Documentation snapshot: 21 September 2026

This Markdown reflects the current implementation. The previously generated
`output/pdf/NEXA-Program-Guide.pdf` is the 18 September snapshot and has not been
regenerated with these research-method updates.

## 1. Purpose and Scope

NEXA is a local Python application that brings together grip-force measurement,
eye tracking, shoulder-movement measurement, and speech analysis. The repository
is named ALS Monitor; the installed command is `nexa`. A shared PyQt5 interface
organizes participants, assessment sessions, results, reports, and baselines.
Each measurement service can also run independently from the command line.

This is a research measurement prototype, not a diagnostic medical device.
Measurements and changes from baseline are descriptive: they do not establish
ALS diagnosis, disease severity, prognosis, or treatment recommendations.
Operator supervision, consistent protocols, and independent measurement
validation remain necessary. No clinical thresholds are established here.

This document describes the implementation in this repository, not planned
features. Hardware-dependent behavior has not all been verified end to end.
The operator-reported Raspberry Pi setup is a Pi 4 Model B Rev 1.5, aarch64,
Debian 13 (Trixie), with a Waveshare OV9281-110 monochrome CSI camera.

### Service Map

- Grip Strength: `als_monitor.grip_monitor`; ESP32 and two load cells; left and right peak force in newtons.
- Oculomotor: `als_monitor.eye_tracker`; CSI dark-pupil or webcam MediaPipe iris tracking; experimental visually guided prosaccade latency.
- Motor / Movement: `als_monitor.shoulder_monitor`; webcam and MediaPipe; 2D arm-elevation velocity.
- Speech: `als_monitor.speech_analysis`; microphone or existing WAV; timing, acoustic estimates, and quality flags.
- NEXA UI: `nexa_ui/app.py`; participant/session workflow, review, baseline comparison, and HTML reports.

### Guide Contents

1. Purpose and scope
2. Architecture and repository
3. Installation and launching
4. Operator workflow and reports
5. Grip measurement and calibration
6. Eye tracking: CSI and webcam
7. Shoulder movement
8. Speech assessment
9. Storage, privacy, and baselines
10. Troubleshooting, limitations, and maintenance
11. Research reproducibility, validation, and references

## 2. Architecture and Repository

The UI does not execute all sensor processing inside its own event loop. It
launches a modality module as a separate `QProcess`, merges standard output and
standard error into a live log, and reads the service's output artifacts.
The service remains responsible for its own capture window and assessment.

```text
nexa command / desktop shortcut
  -> NEXA UI or standalone service
  -> participant and session selection (UI)
  -> preparation -> child process -> review
  -> save artifacts + metrics -> history / report / baseline
```

### Source Layout

```text
scripts/                       Linux and Windows launch/install scripts
nexa_ui/
  app.py                       Application shell and navigation
  screens.py                   Participants, sessions, history, system
  modalities.py                Service registry and metric definitions
  runner.py                    Prepare / run / review process controller
  database.py                  Shared SQLite persistence
  report.py                    Session HTML report generation
  grip_calibration.py          Capture, save, and test calibration
  config.py, theme.py           Paths, display, runtime and visual settings
src/als_monitor/
  grip_monitor/                Serial capture and force graph
  eye_tracker/                 Camera, pupil detection, trials, CSV output
  shoulder_monitor/            Pose detection and velocity analysis
  speech_analysis/             Recording, WAV analysis, CLI and database
    passages/                  Rainbow Passage and metadata
data/                          Models and standalone service data
nexa_data/                     Shared UI database and saved assessments
```

Each service has a `__main__.py`, enabling `python -m als_monitor.<module>`.
The launcher changes to the repository root and adds `src` to `PYTHONPATH`.
UI imports such as `import theme` refer to local files, not a package to install.

The runner sets `NEXA_OUTPUT_DIR`, `NEXA_SESSION_ID`, and, when available,
`NEXA_PARTICIPANT_ID`. Services write into a per-run staging directory. Saving
copies the registered artifacts and `run_log.txt` into a session folder and
records a run in SQLite. Retry/discard removes the staging directory.

The module registry controls commands, output names, displayed metrics,
instructions, and estimated duration. Adding an assessment requires keeping
those definitions consistent with the service's actual artifact schema.

## 3. Installation and Launching

This is a Python project; routine operation does not require compiling the
application. Native dependencies such as OpenCV and MediaPipe must nevertheless
match the machine's architecture, Python version, and CPU capabilities.
The commands below describe the repository's intended setup; package availability
depends on the operating system and enabled repositories.

### Raspberry Pi

From the project directory, install the system dependencies and create an
environment that can access the system Picamera2 packages:

```bash
sudo apt update
sudo apt install python3-picamera2 python3-opencv python3-numpy \
  python3-pyqt5 python3-pygame python3-matplotlib python3-tk \
  python3-venv python3-serial libportaudio2 alsa-utils
cd "$HOME/Documents/ALS Monitor/als-monitor"
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install sounddevice praat-parselmouth
bash scripts/install-launcher.sh
bash scripts/install-desktop-shortcuts.sh
```

Do not recreate or replace an existing working environment unnecessarily.
The Linux installer creates `/usr/local/bin/nexa`; installation persists across
terminal sessions. Moving the repository can require reinstalling the launcher.

```bash
nexa                   # Open the UI
nexa eye               # Prosaccade assessment
nexa preview           # Pupil camera preview
nexa grip              # Grip graph
nexa shoulder          # Shoulder assessment
nexa speech            # Interactive speech menu
nexa help
```

Linux normally uses `.venv/bin/python`, falling back to `python3`. For shoulder
monitoring, the Linux launcher and UI prefer `.venv-shoulder` when present.
Webcam eye tracking also reuses `.venv-shoulder` when available; CSI capture
stays in the Picamera2-capable environment. The UI otherwise uses its own
interpreter for assessments. See Sections 6 and 7 for the MediaPipe setup.
Parselmouth installation on the Pi remains dependent on compatible wheels or
a supported build; the verified Windows installation does not establish Pi support.

### Windows

Use a working Python installation with SQLite support. From PowerShell:

```powershell
py -3 -m pip install numpy opencv-python matplotlib pyserial `
  sounddevice PyQt5 pygame praat-parselmouth
powershell -ExecutionPolicy Bypass -File .\scripts\install-launcher.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\install-desktop-shortcuts.ps1
```

Open a new terminal after installation and run `nexa`. The Windows installer
places a launcher in the user's local Programs directory and updates user PATH.
MediaPipe and its pose model are additional requirements for shoulder capture.
Avoid mixing multiple OpenCV wheel variants in the same environment.

The PowerShell launcher checks `ALS_MONITOR_PYTHON`, an activated environment,
`python`, then `py -3`, accepting an interpreter that imports SQLite and NumPy.
Set `ALS_MONITOR_PYTHON` to an explicit executable if multiple installations
cause confusion. The Windows CLI does not implement the Linux shoulder-specific
environment selection; the UI does recognize `.venv-shoulder/Scripts/python.exe`.

CSI eye capture requires Raspberry Pi Picamera2; webcam eye capture works on
Windows with OpenCV, MediaPipe, pygame, and the face model. Grip needs a Windows serial port such as `COM3`, configured in the
service; the calibration dialog has its own port selection. Speech uses a local
microphone, and shoulder uses OpenCV camera index 0.

## 4. Operator Workflow and Reports

1. Open `nexa` and use Participants to create or select a participant.
2. Start a session, recording the operator and relevant notes.
3. Select Grip Strength, Oculomotor, Motor / Movement, or Speech.
4. Review the operator checklist and participant instruction, then start.
5. Complete the service's own task; monitor the log for errors.
6. Review metrics and output files. Add notes, save, retry, or discard.
7. Use Assessment results to inspect saved runs and manage baselines.
8. Generate a session report or return to History to review earlier sessions.

The runner has preparation, running, and review phases. It supports aborting a
child process and applies a configurable 600-second overall timeout. A process
failure is different from a completed assessment with questionable measurement
quality: always inspect quality flags, valid samples, and the log.

The UI is designed around 1024x600, can be resized, supports 75%-150% zoom,
and uses F11 for fullscreen. Service windows have their own controls and focus.
Countdowns are estimates of the overall workflow, not synchronized hardware
recording clocks. At zero the UI can show `Finishing...` while processing continues.
Grip and motor preparation allowances do not equal actual recording duration.

### History and Analysis

History provides session reports, assessment results, and access to raw folder
locations. Assessment results expose individual runs rather than only the latest
summary on each session tile. Details show the metrics retained by the registry;
the raw summary file can contain additional fields not presented in the UI.

Shoulder review includes Show analysis for the saved velocity PNG. The current
history workflow does not provide that same dedicated plot viewer; the PNG is
available in the raw run folder.

Session reports are self-contained HTML files opened with the system's default
application. They contain participant/session information, run status, metrics,
notes, and speech assessment type. They do not generate diagnoses or reference
range interpretations. The PDF accompanying this guide is documentation, not an
additional built-in assessment-report export feature.

### Baseline Comparison

Select a suitable saved completed run as a baseline, then compare a later run
for the same participant and modality. Speech baselines are separated by task:
connected speech, sustained vowel, and reading. Comparisons display baseline,
current, absolute change, and percentage change where defined. A zero baseline
does not support a meaningful percentage change.

The operator must ensure matching units, calibration, protocol, and algorithms.
The UI does not automatically establish comparability after software or sensor
changes. Old raw-count grip results must not be compared with newton results;
old contour-based shoulder results must not be compared with pose results.

## 5. Grip Measurement and Calibration

The ESP32 sends newline-delimited pairs of raw readings in this order:

```text
right_counts,left_counts
```

The default port is `/dev/ttyUSB0` at 115200 baud. The Python service filters
invalid/nonfinite readings, converts each hand independently, and plots force
against time. It retains left and right maxima and displays elapsed session
duration. Closing the graph ends the service; UI launches produce
`grip_summary.json` with peaks, duration, force unit, and calibration values.
The graph is not a measurement of a physical Y axis: its vertical axis is the
calibrated scalar force from each load-cell channel.

### Conversion to Newtons

```text
zero_counts  = mean unloaded reading
delta_counts = mean known-load reading - zero_counts
scale        = known_mass_kg * 9.80665 / delta_counts
force_N      = abs((raw_counts - zero_counts) * scale * polarity)
```

The calibration retains the signed difference, so either increasing or decreasing
sensor counts can represent loading. The final absolute value makes recorded
force nonnegative. Polarity is retained in the schema but does not alter the
magnitude when it is +1 or -1. A 2 kg reference corresponds to 19.6133 N under
the calibration's standard-gravity assumption.

Absolute value also turns reverse loading and baseline noise into positive
magnitudes; it does not remove drift, preload, or incorrect mechanical leverage.
Validate the complete grip assembly with the load applied along its intended
measurement direction. Factory/default counts are not a substitute for calibration.

Built-in fallback values are left zero -114000 with delta 63000 and right zero
59500 with delta -39200, each using a 2 kg reference. Saved per-hand calibration
overrides these defaults on service startup.

### System Tab Calibration

1. Close any grip service using the serial port, then open System > Calibrate grips.
2. Select the port, hand, and known reference mass.
3. Remove load and capture the unloaded reading.
4. Apply the known load steadily and capture the loaded reading.
5. Save the calibrated hand; the other hand need not be recalibrated.
6. Use Test calibration to inspect live newtons against the expected reference force.

Capture averages fresh serial readings (50 samples), includes a connection
settling delay, and rejects an insufficient load difference. Retaring invalidates
that hand's unfinished calibration. Saving merges complete hands with existing
saved data, preserving the other hand. Test mode can use completed unsaved or
saved calibration. Settings are stored in `nexa_data/grip_calibration.json`.

The exported grip summary currently contains peaks and total elapsed duration,
not a persistent full force-time trace, contraction duration, or validated
fatigue/consistency score. Some checklist text still names Arduino Uno even
though the configured deployment uses an ESP32.

## 6. Eye Tracking: CSI and Webcam

CSI is the default. The UI offers CSI camera or Webcam before an oculomotor run;
the CLI accepts `--camera csi` or `--camera webcam`. The backend is selected
explicitly: failure does not silently switch to a different sensor or algorithm.

### CSI Dark-Pupil Pipeline

The eye module selects a unique Picamera2 camera whose model contains `ov9281`.
It does not silently fall back to a USB webcam. The Waveshare OV9281-110 is the
identified deployment sensor. Defaults request 640x400 YUV420, 120 FPS, 4000 us
manual exposure, and gain 4. Requested frame rate is not guaranteed achieved
frame rate; inspect recorded sample intervals.

`camera.py` extracts grayscale frames and maps sensor timestamps into the
monotonic timing domain when available, with receive-time fallback. The sampler
feeds pupil observations to the task. `pupil_tracker.py` uses image thresholding,
morphology, and geometric/confidence filtering rather than a learned gaze model.

The default image pipeline uses a 5-pixel Gaussian blur, adaptive dark-pixel
thresholding, and a 5-pixel elliptical morphological kernel. Configuration sets
the dark percentile to 2%, threshold offset to 12, and threshold limits to
10-110 grayscale levels. Candidate filters include area 150-20000 pixels squared,
circularity at least 0.55, fill at least 0.45, and confidence at least 0.35.
These are project heuristics dependent on image scale and framing, not published
clinical decision thresholds. Source: `eye_tracker/pupil_tracker.py` and `config.py`.

### Webcam Face/Iris Model

Webcam mode uses OpenCV camera 0 by default; this can be a built-in camera rather
than USB on a laptop. `--webcam-index` is an optional override. Capture requests
do not guarantee the camera's achieved resolution or FPS. The tracking model is
Google MediaPipe Face Landmarker, configured for one face in VIDEO mode with
face blendshapes enabled. This is pretrained inference, not a model trained or
fine-tuned on NEXA participants. Google documents 478 face landmarks; the
implementation selects the anatomical right iris center at index 468 or left
at 473 and four surrounding points. [Face Landmarker guide](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python)

The model artifact is `data/models/face_landmarker.task`, from Google's
`face_landmarker/face_landmarker/float16/1` bundle; `NEXA_FACE_MODEL` can override
it. `scripts/setup-eye-webcam.sh` downloads the model and adds pygame to the
existing `.venv-shoulder` environment without upgrading MediaPipe. Shoulder
monitoring does not need to run; only its compatible Python environment is reused.

```bash
bash scripts/setup-eye-webcam.sh
nexa preview --camera webcam
nexa eye --camera webcam
```

Current preprocessing converts webcam frames to grayscale, then replicates them
to RGB for the face model. This differs from feeding native color images and
requires validation under intended lighting. Display flips are undone before
inference and reapplied to coordinates so anatomical eye selection is retained.
Missing/incomplete faces, nonfinite/out-of-frame iris points, and an available
selected-eye blink blendshape score of at least 0.5 invalidate the observation.
The reported iris radius is the mean distance to the four surrounding landmarks.
Accepted samples use confidence 1, a binary acceptance marker, not a calibrated
iris-detection probability. Blink filtering is a project heuristic.

Coordinates are image pixels, not screen-gaze points, gaze angles, or a
head-motion-corrected eye-rotation signal. Keep the full face visible and head
position stable. Head movement can look like eye movement. Pixel thresholds
developed for a close-up CSI eye image may not transfer to a full-face webcam.
Backend and tracking method are saved in the eye summary; compare modalities
separately until cross-backend equivalence has been demonstrated.

### Preview and Assessment

```bash
rpicam-hello --list-cameras
nexa preview
nexa eye
```

Preview overlays the pupil/iris position and estimated FPS. B toggles the binary
mask for the CSI detector; no binary mask is generated by Face Landmarker.
Q or Escape exits. The assessment includes camera feedback and a fixation
quality check, followed by 10 trials with targets in left/right/up/down directions.
Space advances task stages. Keep head position, lighting, and camera framing stable.

The detector estimates saccade onset using a velocity threshold with an adaptive
baseline component, minimum duration/sample count, direction/displacement checks,
and latency limits. These are configurable research parameters, not clinical
cutoffs. Pupil velocity is in pixels/second, not calibrated gaze degrees/second.
Summary statistics include valid/invalid trial counts, mean latency, standard
deviation, coefficient of variation, and minimum/maximum latency.

### Onset Detection and Timing Parameters

The custom detector filters valid observations, applies a centered three-sample
moving average, and computes Euclidean pixel speed using central differences
(one-sided at endpoints). A 0.30-second pre-target interval supplies baseline
position and speed. The speed threshold is the greater of 120 pixels/second and
baseline mean speed plus five baseline standard deviations. A candidate requires
at least three consecutive above-threshold samples spanning at least 20 ms.
Onset is sought from 70 to 800 ms after target presentation. Direction validation
requires at least 6 pixels of signed displacement within 150 ms and limits
off-axis displacement to a ratio of 1.5. These defaults are configurable.

The quality gate requires at least 15 valid samples overall, eight baseline
samples, and a median sample interval no greater than 25 ms. Therefore a 30 FPS
webcam is suitable for preview but commonly fails the assessment's sampling
gate. The requested target is 120 FPS; 60 FPS may pass, but camera rate alone
does not establish effective sampling rate after model inference.

Latency is `1000 * (detected_onset_time - target_onset_time)`, in milliseconds.
CSI prefers sensor timestamps mapped to the monotonic clock and can fall back
to receive time. Webcam timestamps are assigned after frame receipt; exposure,
USB buffering, and driver latency are not independently corrected. Target onset
uses software timing, not a photodiode measurement. The display-latency
compensation default is zero. Centered smoothing can shift onset estimates,
and median-interval gating does not rule out isolated long gaps. Validate the
full timing chain against an external reference before claiming millisecond
accuracy. Source: `eye_tracker/saccade_detector.py`, `camera.py`, and `config.py`.

UI runs create `eye_results.csv`, `eye_summary.json`, and optionally
`eye_samples.csv`. Important current limitation: the UI registry collects only
the first two files, so the sample CSV is not preserved by the normal save flow
before staging cleanup. Standalone runs save timestamped trial, sample, and
summary CSV files under `results/`.

### CSI Configuration and Current Hardware Status

The deployment configuration uses the following in `/boot/firmware/config.txt`:

```ini
[all]
camera_auto_detect=0
dtoverlay=ov9281
```

This Waveshare setup uses the plain OV9281 overlay, not an Arducam-specific
option. Shut down and unplug the Pi before touching camera connectors.

As of this documentation snapshot, replacing the ribbon enabled sensor detection,
but video capture still timed out in both NEXA and an independent 30 FPS
`rpicam-still --nopreview` test. This remains unresolved; it is not documented
as working capture. Hardware, connector, and kernel/driver compatibility require
isolation using a known-good camera/Pi or a spare OS card.

The SHARPNESS/no sharpen algorithm message is distinct from a frontend timeout.
An invalid `DISPLAY` value prevents preview rendering but does not explain the
observed headless capture timeout. An `ov9282` driver label does not by itself
mean the selected OV9281 camera model is wrong.

## 7. Shoulder Movement

The shoulder service uses a USB webcam through OpenCV camera index 0 and
MediaPipe Pose Landmarker. The model is loaded from
`data/models/pose_landmarker_lite.task`, or the `NEXA_POSE_MODEL` override.
It detects anatomical shoulders and wrists, filters low-confidence landmarks,
and mirrors the displayed image while retaining anatomical side labels.

### Model and Measurement Definition

The selected artifact is Google's Pose Landmarker Lite float16 version-1 task
bundle (`pose_landmarker/pose_landmarker_lite/float16/1`). MediaPipe provides
33 body landmarks; NEXA uses image-coordinate shoulders 11/12 and wrists 15/16,
not its world-coordinate output. The task runs in VIDEO mode for one pose.
Landmark presence and visibility must each be at least 0.6 and normalized x/y
must be within the image. These are filtering criteria, not calibrated joint
position error bounds. [Pose Landmarker guide](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker)

The pretrained network estimates landmarks only; the angle and velocity formulas
are project code. For shoulder-to-wrist vector `(dx, dy)` in image pixels, with
positive image y downward, elevation is the angle to downward vertical:
`acos(dy / sqrt(dx*dx + dy*dy))`, expressed in degrees. Angular speed is the
absolute finite difference of successive valid angles divided by elapsed seconds.
Pixel aspect ratio, perspective, body rotation, and a bent elbow affect this
proxy; it is not isolated glenohumeral range of motion. NEXA does not train an
ALS-specific pose model or classify movement impairment.

Select L or R for the evaluated arm. Press Space or click Start to arm a trial;
the service waits for the required landmarks before recording. Keep the selected
shoulder and wrist visible. Recording lasts five seconds. Q exits.

The measurement is shoulder-to-wrist elevation relative to image vertical in
two dimensions. Angular speed uses absolute angle change over elapsed time,
with a three-sample moving average for the peak. Missing tracking resets the
previous-angle state. At least three valid velocity samples are required for
a result. This is not a 3D shoulder joint angle or a full biomechanical model.

Artifacts are `shoulder_summary.json`, `shoulder_velocity.csv`, and
`shoulder_analysis.png`. The plot shows raw angular speed, smoothed speed, and
peak reference in deg/s. The service also uses `nexa_evaluations.db`; standalone
plot/CSV artifacts are placed under `data/shoulder_monitor/`.

### Raspberry Pi-Compatible Runtime

The reported Python 3.13 / MediaPipe 1.0.1 installation terminated with a native
AES/illegal-instruction failure on this Pi. A separate Python 3.12 environment
with MediaPipe 0.10.14 was reported to run the shoulder service successfully.
This is a deployment workaround, not a guarantee for all Pi environments.

```bash
cd "$HOME/Documents/ALS Monitor/als-monitor"
.venv/bin/python -m pip install uv
.venv/bin/uv python install 3.12
.venv/bin/uv venv --python 3.12 .venv-shoulder
.venv/bin/uv pip install --python .venv-shoulder/bin/python \
  "numpy<2" "opencv-contrib-python<4.12" \
  "mediapipe==0.10.14" matplotlib
```

Download the pose model once if absent:

```bash
mkdir -p data/models
MODEL_BASE=https://storage.googleapis.com/mediapipe-models/pose_landmarker
MODEL_PATH=pose_landmarker_lite/float16/1/pose_landmarker_lite.task
curl -fL "$MODEL_BASE/$MODEL_PATH" \
  -o data/models/pose_landmarker_lite.task
```

Linux `nexa shoulder` and motor assessments in the UI select `.venv-shoulder`
when its executable exists; webcam eye tracking also reuses that environment.
Close and reopen the UI after updating launcher/configuration code. A missing
dedicated environment falls back to the default interpreter, potentially
reintroducing the incompatible MediaPipe build.

Keep framing and movement plane consistent across sessions. Out-of-plane motion,
occlusion, frame timing, and detection noise can change estimates. Three valid
samples are a technical minimum, not evidence of adequate trial coverage.

## 8. Speech Assessment

The speech UI records new assessments or analyzes existing WAVs without microphone
capture. Select the correct task; its label is retained in results and reports.

### Tasks

- Connected speech: speak naturally about a familiar topic; UI default 30 seconds.
- Sustained vowel: hold an "ah" at comfortable pitch and volume; UI default 5 seconds.
- Reading: read the bundled Rainbow Passage at a normal pace; UI default 60 seconds.

The passage appears during reading, not preparation. All tasks have operator
checklists and instructions. Keep microphone position and room noise consistent.

Recording uses `sounddevice`, mono PCM16 WAV, and a 180-second cap. It prefers
48000 Hz, with fallback to a supported device default; file headers and analysis
use the actual rate. `MIC_DEVICE_INDEX` selects a nondefault microphone.

### Analysis Implemented

The WAV reader accepts 16-bit PCM WAV and averages multichannel input to mono.
It calculates recording duration, RMS level in dBFS, clipping fraction, estimated
speech duration, internal pause duration/count/percentage, mean fundamental
frequency (F0), Praat HNR, voiced pitch-frame count, and valid HNR-frame count.

Speech timing uses RMS-energy thresholding in 30 ms frames, removes short speech
bursts, and counts qualifying pauses between the first and last detected speech.
The active minimum pause setting is 0.150 seconds; speech bursts shorter than
0.100 seconds are removed. For frame RMS values, the threshold is
`max(10^(QC_MIN_RMS_DBFS/20), min(2.5*P20(RMS), 0.5*P80(RMS)))`.
The cap prevents a steady vowel from setting its own threshold above its signal
level, but this energy gate is still noise-sensitive and is not WebRTC VAD.
Leading/trailing silence is excluded from pause counts; pause percentage divides
internal pause time by the whole recording duration. This distinction matters
when comparing another tool's pause fraction or speaking-time definition.

Warnings cover short/quiet recordings, clipping, insufficient speech, and missing
F0/HNR, even on successful runs. F0/HNR now use Praat through the
`praat-parselmouth` package; timing and RMS/clipping remain project calculations.

### Praat F0 and HNR Methods

The implementation calls `Sound.to_pitch_ac` (raw autocorrelation) and
`Sound.to_harmonicity_cc` (cross-correlation harmonicity) on the whole
mono-averaged signal at its native sample rate. It does not resample, trim a
stable vowel segment automatically, or apply the separate RMS speech mask to
Praat frames. These are deterministic signal-processing methods, not learned
speech models. [Parselmouth API](https://parselmouth.readthedocs.io/en/stable/api_reference.html)

| Parameter | Current setting |
|---|---|
| Pitch method | Praat raw autocorrelation |
| Pitch floor / ceiling | 75 / 500 Hz |
| Pitch time step | Automatic (`None`, configured as 0.0) |
| HNR method | Praat cross-correlation |
| HNR time step | 0.01 s |
| HNR minimum pitch | 75 Hz |
| HNR silence threshold | 0.1 (relative amplitude criterion, not dBFS) |
| HNR periods per window | 1.0 |
| Aggregation | Arithmetic mean of valid frames, separately for each measure |

Unspecified pitch options retain the installed Parselmouth defaults; archive
that version alongside the explicit settings. F0 excludes zero/unvoiced and
nonfinite values. HNR excludes nonfinite values and Praat's -200 undefined
sentinel; genuine negative HNR remains valid data and is not absolute-valued.
Unlike grip force, HNR is a logarithmic ratio and must retain its sign.
F0 and HNR can have different valid-frame sets and counts.

F0 is measured in Hz; HNR in dB, conceptually
`10 * log10(periodic_power / noise_power)`. Higher pitch does not imply higher
HNR. HNR is not recording level (`rms_dbfs`) or calibrated sound pressure level.
Praat documents cross-correlation harmonicity as its preferred harmonicity
command. [Praat Harmonicity manual](https://www.fon.hum.uva.nl/praat/manual/Harmonicity.html)

NEXA's selected raw-autocorrelation pitch method is explicitly named rather
than described as the newest recommended method for every speech task. Modern
Praat distinguishes filtered autocorrelation for intonation from raw methods
for other voice/periodicity analyses. Method choice should follow the study's
measurement objective. [Praat pitch-method guidance](https://www.fon.hum.uva.nl/praat/manual/how_to_choose_a_pitch_analysis_method.html)

Very short recordings are not padded to fabricate frames: pitch is skipped below
`3 / pitch_floor` seconds, and HNR below `(1 + periods_per_window) / minimum_pitch`.
No valid estimate becomes JSON null and triggers the corresponding quality flag.
Current checks flag duration below 1 s, RMS below -45 dBFS, clipping fraction
above 0.001, estimated speech below 1 s, and missing F0/HNR. The configured
minimum-valid-frame-percentage constants are not currently enforced; `VALID`
means no implemented warning fired, not that research validity is established.

### Versioning and Reference Check

Speech module version `0.2.0-praat` records `analysis_parameters`, Parselmouth
and embedded Praat versions, method names, explicit settings, aggregation, and
channel/segment policy. Metadata is retained in the speech database and summary
JSON and exposed through UI metric details. The verified Windows environment
used Parselmouth 0.4.7 with Praat 6.1.38. Other deployments must record their
actual versions; the dependency is not globally pinned by this documentation.

On one operator-supplied 7.2-second, 48 kHz stereo PCM16 test recording, the old
custom estimator produced 9.5705 dB HNR; the new Praat path produced 13.6891 dB
and mean F0 114.3966 Hz. The operator reported PhonaLab HNR of 13.7 dB for that
file, so the new result agrees at the displayed precision. PhonaLab states that
it uses Parselmouth/Praat, but its complete per-analysis settings have not been
independently established here. This single-file comparison is an engineering
check, not a validation cohort, clinical accuracy claim, or proof of identical
outputs on other recordings. [PhonaLab methods FAQ](https://www.phonalab.com/en/faq)

Old custom results (including versions that returned a median under a mean-F0
field name) are not automatically rewritten. Reanalyze both baseline and follow-up
WAVs with the same method/settings; do not apply a fixed dB correction or pool
legacy and Praat results. Keep original results with their provenance.

All three tasks currently share the acoustic analysis core. Reading recordings
also attach passage metadata in the record-and-assess flow; uploaded reading
WAVs do not pass through that metadata-enrichment branch. The system does not
currently implement transcription, verified words per minute, reading accuracy,
word alignment, jitter/shimmer, or diagnostic speech classification.

### Command-Line Operations

```bash
nexa speech
nexa speech list-microphones
nexa speech init-db
nexa speech record --task sustained_vowel --duration 5
nexa speech assess --task reading --duration 60
nexa speech analyze-speech recording.wav
nexa speech analyze-sustained-vowel vowel.wav
nexa speech analyze-reading reading.wav
nexa speech show-results
nexa speech --help
```

`record` records only; `assess` records and analyzes. `analyze` is also available
as a general WAV-analysis command. Analysis commands accept participant,
session ID, and baseline options. Standalone baseline comparison uses:

```bash
nexa speech analyze-speech baseline.wav --participant P001 --baseline
nexa speech analyze-speech followup.wav --participant P001 --session-id FOLLOWUP
nexa speech compare-baseline P001 FOLLOWUP
```

The standalone speech database and its baseline flags are separate from UI
baseline selections. Prefer the UI baseline workflow for UI-managed sessions.
Saved UI speech runs retain `speech_recording.wav` and `speech_summary.json`.

## 9. Storage, Privacy, and Baselines

### Shared UI Data

```text
nexa_data/
  nexa.sqlite3                 Participants, sessions, runs, baselines
  grip_calibration.json        Per-hand force calibration
  staging/<modality_stamp>/    Temporary run outputs
  raw/session_00001/<run>/     Saved artifacts and run_log.txt
  reports/                    Generated HTML reports
```

SQLite holds participant records, session metadata, run status, timestamps,
metric JSON, operator notes, artifact locations, and baseline references.
Raw files remain ordinary local files rather than SQLite BLOBs. Back up the
database and raw directories together with calibration settings.

### Standalone Service Data

- Speech: `data/speech_analysis/`, including recordings and `database/nexa_speech.db`.
- Shoulder: `nexa_evaluations.db` plus `data/shoulder_monitor/` plot/CSV outputs.
- Eye: timestamped files under the working-directory-relative `results/` folder.
- Grip: interactive graph and console output; JSON export depends on `NEXA_OUTPUT_DIR`.

UI execution can also produce service-specific database entries. Discarding a
UI run does not roll back those independent records. Speech database audio paths
may refer to staging locations removed after saving/discarding; use the copied
WAV in the UI raw folder as the retained recording for saved UI runs.

### Handling Sensitive Data

Recordings, identifiers, notes, and measurements can be sensitive. Use coded
participant identifiers, obtain appropriate permission for capture/storage,
restrict machine access, and apply an explicit retention and backup policy.
No built-in user-account access control, database encryption, or automated
retention service is established by the inspected implementation.

`.gitignore` excludes `nexa_data/`, databases, and most `data/` content. This is
not encryption and does not remove previously committed files from Git history.
Standalone `results/` and `.venv-shoulder/` are not explicitly excluded in the
current ignore file; check `git status` before committing. Do not commit real
recordings, participant data, local environments, or hardware secrets.

Move or back up datasets with their directory structure intact. Stored absolute
artifact paths may need adjustment after moving the repository or transferring
a dataset to a different machine. The code does not provide a complete portable
dataset migration workflow.

## 10. Troubleshooting, Limitations, and Maintenance

### Common Failure Checks

- Command not found: rerun the platform launcher installer; on Windows open a new terminal to reload PATH.
- Missing Python package: install into the interpreter actually used by that service, not an unrelated global Python.
- Shoulder illegal instruction: use the tested dedicated environment; native CPU incompatibility is not fixed by downloading the model again.
- Shoulder does not start: focus its window, use Space/Start, select L/R, and ensure the required landmarks are visible.
- Grip has no graph updates: verify serial port/baud, exclusive port access, and newline-delimited right,left numeric readings.
- Grip sign or magnitude is wrong: tare unloaded, calibrate each hand with a known load, and test the reference force before assessment.
- Speech sample-rate error: inspect the selected microphone and actual supported rate; the recorder prefers 48000 Hz with fallback.
- Camera not detected: check model/overlay, ribbon orientation, and boot logs before changing Python packages.
- Camera frontend timeout: distinguish camera registration from successful frame delivery; test capture outside NEXA with no preview.
- Preview unavailable: use a real graphical desktop session; a placeholder DISPLAY value is not a valid display connection.
- Report does not open: inspect the generated HTML path and the system's default browser/file association.

### Verification Checklist

Before collecting a new dataset, exercise one complete UI run per modality,
including save, reopen in History, report generation, and baseline comparison.
For speech, test each task and existing-WAV upload, and verify the retained WAV.
For grip, test each hand independently at zero and known load. For shoulder,
verify anatomical labels and the plot/CSV. For eye tracking, verify sustained
frame delivery, pupil detection, sample intervals, and valid-trial reasons.

Run those checks on the actual target machine. Import success does not prove
that a native library can initialize, and camera enumeration does not prove
that image streaming works. No comprehensive automated hardware test suite is
included in the inspected repository.

### Known Product Boundaries

The countdown is estimated, some UI instructions retain older terminology,
and only registered artifacts/metrics survive the normal UI collection flow.
Baselines do not enforce algorithm-version or unit equivalence. Calibration
is linear and does not compensate for creep, hysteresis, or temperature drift.
Camera-derived measurements depend on lighting, framing, and reliable timing.
Speech quality labels are not clinical judgments.

### Source of Truth

This guide was assembled from the repository's scripts, configuration, service
implementations, UI, storage layer, and README, together with the operator's
reported hardware troubleshooting. It does not include private session contents.
For exact current defaults, consult the relevant configuration/source file.
README.md remains the shorter setup reference; ABOUT.md is the editable source
for the accompanying program-guide PDF.

## 11. Research Reproducibility, Validation, and References

### Algorithm Inventory

| Measurement | Algorithm/model | Output interpretation |
|---|---|---|
| Grip | Per-hand linear known-load calibration and absolute magnitude | Scalar force in N; no anatomical force vector |
| CSI eye | Dark threshold, morphology, shape scoring; custom velocity onset detector | Pupil image coordinates and experimental latency |
| Webcam eye | Pretrained MediaPipe Face Landmarker; custom blink/iris selection and onset detector | Iris image coordinates; not calibrated gaze |
| Shoulder | Pretrained MediaPipe Pose Landmarker Lite; project angle differentiation | 2D elevation-speed proxy in deg/s |
| Speech F0 | Praat raw autocorrelation via Parselmouth | Mean valid-frame fundamental frequency in Hz |
| Speech HNR | Praat cross-correlation harmonicity via Parselmouth | Mean valid-frame harmonicity in dB |
| Speech timing | Project RMS-energy segmentation | Estimated speech and internal pauses, not lexical timing |

Pretrained landmark inference is not equivalent to validation for ALS research.
No participant-specific model fitting, disease classifier, ALS severity model,
or prediction of progression is implemented. The upstream models' performance
does not establish NEXA accuracy on its intended population or hardware.

### Recommended Study Record

For a reproducible methods section and dataset manifest, retain:

- Repository commit, operating system, architecture, Python executable/version, and installed package versions.
- MediaPipe task-bundle source, local SHA-256 checksum, selected backend, and all modified configuration values.
- Camera model, achieved frame/sample intervals, image size, exposure, gain, lighting, head support, and viewing geometry.
- Microphone model, distance/orientation, input gain, audio enhancements, actual sample rate, channel conversion, task, and analyzed segment.
- Grip reference mass, calibration date, unloaded/loaded counts per hand, fixture geometry, and independent check-load readings.
- Raw recordings/traces where retained, quality flags, invalid-trial reasons, valid-frame counts, run logs, and operator deviations.

These are recommended research records, not a claim that every item is already
automatically captured. Speech currently stores richer algorithm metadata than
the other services. Model checksums and a complete environment manifest are not
automatically embedded in each assessment. The eye raw-trace UI retention gap
described in Section 6 should be resolved before relying on saved sessions for
reprocessing. Use de-identified manifests and protected storage for raw data.

### Validation Plan, Not Completed Validation

Define intended endpoints and acceptable error before data collection. Separate
software correctness, reference-method agreement, repeatability, and clinical
validity: passing one does not establish the others.

- Grip: test several independent loads across the intended range, both loading and unloading, repeated zero returns, and left/right channels. Quantify bias, repeatability, hysteresis, and drift; absolute value can hide sign reversals.
- Eye: compare actual target-display and eye-motion timing to an external reference. Evaluate CSI and webcam separately, including head motion, blinks, glasses, illumination, dropped frames, and invalid-trial rate.
- Shoulder: compare the defined 2D proxy with a suitable reference in a controlled movement plane; separately investigate out-of-plane motion, occlusion, elbow flexion, and tracking loss. Do not claim a 3D joint-angle validation from a 2D comparison.
- Speech: compare matched WAVs, channels, segments, and settings against direct Praat over diverse pitches, noise levels, tasks, and recording conditions. Report paired differences and error distributions, not only correlation or one rounded match.

Report sample size, exclusions, units, per-task/backend results, and uncertainty.
Define an acceptable error margin for the intended use rather than deriving it
after seeing results. Do not treat nominal camera FPS, model confidence, or a
`VALID` label as a metrological accuracy guarantee. If methods change, preserve
the previous version and reprocess raw baselines consistently.

### Primary References and Citation Notes

References describe the upstream methods; repository code defines NEXA's
specific integration, preprocessing, filtering, and aggregation. Cite the
software version actually used in an experiment, not merely this guide's date.

1. Jadoul, Y., Thompson, B., and de Boer, B. (2018). Introducing Parselmouth: A Python interface to Praat. *Journal of Phonetics*, 71, 1-15. [DOI](https://doi.org/10.1016/j.wocn.2018.07.001).
2. [Parselmouth API reference](https://parselmouth.readthedocs.io/en/stable/api_reference.html): `Sound`, `to_pitch_ac`, and `to_harmonicity_cc`; use installed-version defaults when reproducing the analysis.
3. [Praat Harmonicity manual](https://www.fon.hum.uva.nl/praat/manual/Harmonicity.html) and [pitch-method selection](https://www.fon.hum.uva.nl/praat/manual/how_to_choose_a_pitch_analysis_method.html): definitions and distinctions among analysis methods.
4. [Google MediaPipe Face Landmarker Python guide](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python): face/iris landmark inference and VIDEO-mode interface.
5. [Google MediaPipe Pose Landmarker guide](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker): body landmarks and model family. NEXA selects the Lite task bundle and uses only the image-coordinate subset described above.
6. [PhonaLab FAQ](https://www.phonalab.com/en/faq): the provider's description of its use of Parselmouth/Praat. The operator's reported comparison value is not a substitute for independent reference testing.

The grip conversion, RMS timing gate, and saccade threshold rules are project
implementations. They should not be presented as a named published clinical
standard without a separate validated protocol and supporting evidence.
