# ALS Monitor

Monitoring services for eye tracking, grip force, shoulder movement, and
speech analysis, with a shared NEXA user interface.

## Raspberry Pi setup

From the Raspberry Pi terminal:

```bash
sudo apt update
sudo apt install -y \
  python3-picamera2 \
  python3-opencv \
  python3-numpy \
  python3-pyqt5 \
  python3-pygame \
  python3-matplotlib \
  python3-tk \
  python3-venv \
  libportaudio2 \
  alsa-utils \
  python3-serial
```

Open the project directory:

```bash
cd "$HOME/Documents/ALS Monitor/als-monitor"
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install sounddevice
```

Run all commands below from this directory.

## Install the launcher

Run this once using the project's location on the Raspberry Pi:

```bash
bash "$HOME/Documents/ALS Monitor/als-monitor/scripts/install-launcher.sh"
```

After installation, start any service from any directory:

```bash
als-monitor ui
als-monitor eye
als-monitor preview
als-monitor grip
als-monitor shoulder
als-monitor speech
```

Run `als-monitor` without an option to open the NEXA user interface directly.
The launcher automatically finds the project, changes directory, and sets
`PYTHONPATH`.

On Raspberry Pi, the launcher automatically uses `.venv/bin/python` when
available, falling back to `python3` otherwise. Desktop shortcuts use the same
launcher, so no environment activation is needed. `--system-site-packages`
allows the environment to access Picamera2 and the other APT-installed libraries.

NEXA opens at its intended `1024x600` size and can be resized like a normal
window. Use the sidebar `-`, percentage, and `+` controls to zoom from 75% to
150%. Keyboard controls are `Ctrl+-`, `Ctrl+0`, and `Ctrl++`; `F11` toggles
fullscreen mode.

## Windows setup

### 1. Install Python

Install Python 3 from [python.org](https://www.python.org/downloads/windows/).
During installation, enable **Add Python to PATH**.

Confirm that the Python launcher works:

```powershell
py -3 --version
```

### 2. Install dependencies

Open PowerShell and install the Windows packages:

```powershell
py -3 -m pip install --upgrade pip
py -3 -m pip install numpy opencv-python matplotlib pyserial sounddevice PyQt5 pygame
```

The Raspberry Pi-only `picamera2` package should not be installed on Windows.

### 3. Open the project

Change this path if the repository is stored elsewhere:

```powershell
Set-Location "C:\Users\Ervin\Documents\ALS Monitor"
```

### 4. Install the Windows launcher

Run the installer once from the project directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-launcher.ps1
```

Open a new PowerShell or Command Prompt window so the updated user `PATH` is
loaded. The launcher then works from any directory:

```powershell
als-monitor
als-monitor ui
als-monitor grip
als-monitor shoulder
als-monitor speech
```

Running `als-monitor` without a service opens the NEXA user interface directly.

To run without installing the launcher:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\als-monitor.ps1 grip
```

### 5. Install desktop shortcuts

Create native Windows shortcuts for NEXA UI and the monitoring services:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-desktop-shortcuts.ps1
```

### Windows hardware notes

- **Grip monitor:** Find the ESP32 port in Device Manager, then set
  `SERIAL_PORT` in `src/als_monitor/grip_monitor/main.py` to a value such as
  `COM3`.
- **Shoulder monitor:** Connect a webcam recognized by Windows. The service
  uses camera index `0` by default.
- **Speech analysis:** Connect a microphone and run
  `als-monitor speech list-microphones` before recording.
- **Eye tracker:** The current eye-camera driver uses Raspberry Pi Picamera2.
  Eye capture and preview are therefore unavailable on Windows.

### Windows troubleshooting

If `als-monitor` is not recognized, close and reopen the terminal. You can also
rerun `install-launcher.ps1` after moving the project.

If PowerShell blocks a script, use the provided one-command bypass:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\als-monitor.ps1 help
```

If Python reports a missing module, rerun the dependency installation with the
same `py -3 -m pip` command shown above. This ensures packages are installed for
the interpreter used by the launcher.

Verify that the selected Python installation is healthy:

```powershell
py -3 -c "import sqlite3, numpy; print('Python OK')"
```

If Anaconda or another Python installation is broken, point ALS Monitor to a
working interpreter:

```powershell
$env:ALS_MONITOR_PYTHON = "C:\Path\To\Python\python.exe"
als-monitor speech
```

To persist that selection for future terminals:

```powershell
[Environment]::SetEnvironmentVariable(
    "ALS_MONITOR_PYTHON",
    "C:\Path\To\Python\python.exe",
    "User"
)
```

## Install desktop buttons

Create a desktop shortcut for the complete NEXA interface, plus shortcuts for
the individual monitoring services, with one command:

```bash
bash "$HOME/Documents/ALS Monitor/als-monitor/scripts/install-desktop-shortcuts.sh"
```

This adds the following buttons to the Raspberry Pi desktop:

- `NEXA UI` (the complete application)
- `ALS Eye Tracker`
- `ALS Grip Monitor`
- `ALS Shoulder Monitor`

Double-click `NEXA UI` to open the complete application. The individual service
buttons open a terminal and start their service directly. If the desktop asks
whether to launch a file, select **Execute**.

## Eye tracker

Check the camera first:

```bash
rpicam-hello --list
```

Open the pupil-detection preview:

```bash
PYTHONPATH=src python3 -m als_monitor.eye_tracker.preview
```

Start the eye-tracking test:

```bash
PYTHONPATH=src python3 -m als_monitor.eye_tracker
```

- Press `Space` to continue or begin a test.
- Press `B` in preview mode to toggle the pupil mask.
- Press `Q` or `Esc` to exit.
- Results are saved in `results/`.

## Grip monitor

Connect the ESP32 and verify its serial port:

```bash
ls -l /dev/ttyUSB* /dev/ttyACM*
```

The default is `/dev/ttyUSB0` at `115200` baud. Change `SERIAL_PORT` in
`src/als_monitor/grip_monitor/main.py` when necessary.

Start the grip graph:

```bash
PYTHONPATH=src python3 -m als_monitor.grip_monitor
```

The ESP32 must send right, then left, as two comma-separated readings:

```text
124.8,118.3
```

Close the graph window to stop the service.

## Shoulder monitor

Connect a USB webcam and run:

```bash
PYTHONPATH=src python3 -m als_monitor.shoulder_monitor
```

- Enter the participant ID and select `LEFT` or `RIGHT`.
- Press `Space` to start a five-second trial.
- Press `Q` to exit.
- Results are saved in `nexa_evaluations.db`.

## Speech analysis

Open the interactive speech menu:

```bash
als-monitor speech
```

The menu includes microphone discovery, database setup, recording, acoustic
analysis, stored results, baseline comparison, help, and exit.

List available microphones:

```bash
als-monitor speech list-microphones
```

Create the speech-analysis database:

```bash
als-monitor speech init-db
```

Show all available speech commands:

```bash
als-monitor speech --help
```

Record and analyze audio directly:

```bash
als-monitor speech record --task sustained_vowel --duration 5
als-monitor speech analyze-sustained-vowel path/to/recording.wav
als-monitor speech analyze-speech path/to/recording.wav
```

Create a participant baseline and compare a later session:

```bash
als-monitor speech analyze-speech baseline.wav --participant P001 --baseline
als-monitor speech analyze-speech followup.wav --participant P001 --session-id P001_FOLLOWUP
als-monitor speech compare-baseline P001 P001_FOLLOWUP
```

This remains a research prototype. Its acoustic measurements are descriptive
and are not validated diagnostic or clinical thresholds.

## Project structure

```text
src/als_monitor/
|-- eye_tracker/
|-- grip_monitor/
|-- shoulder_monitor/
`-- speech_analysis/
```

This project is a measurement prototype and is not a diagnostic medical device.
