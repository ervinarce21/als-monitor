# ALS Monitor

Raspberry Pi services for eye tracking, grip-force monitoring, and shoulder
movement monitoring.

## Install

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
  python3-sounddevice \
  libportaudio2 \
  alsa-utils \
  python3-serial
```

Open the project directory:

```bash
cd ~/als-monitor
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

Run `als-monitor` without an option to use an interactive menu. The launcher
automatically finds the project, changes directory, and sets `PYTHONPATH`.

## Install desktop buttons

Create clickable buttons for all three services with one command:

```bash
bash "$HOME/Documents/ALS Monitor/als-monitor/scripts/install-desktop-shortcuts.sh"
```

This adds the following buttons to the Raspberry Pi desktop:

- `ALS Eye Tracker`
- `ALS Grip Monitor`
- `ALS Shoulder Monitor`

Each button opens a terminal and starts its service. If the desktop asks
whether to launch the file, select **Execute**.

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

The menu includes microphone discovery, database setup, recording, all analysis
commands, stored results, baseline comparison, help, and exit. Analysis stages
that are still under development report their implementation status.

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

The speech module is currently a staged research prototype. Commands marked as
future steps report that they are not yet implemented.

## Project structure

```text
src/als_monitor/
|-- eye_tracker/
|-- grip_monitor/
|-- shoulder_monitor/
`-- speech_analysis/
```

This project is a measurement prototype and is not a diagnostic medical device.
