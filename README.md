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
  python3-pygame \
  python3-matplotlib \
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
als-monitor eye
als-monitor preview
als-monitor grip
als-monitor shoulder
```

Run `als-monitor` without an option to use an interactive menu. The launcher
automatically finds the project, changes directory, and sets `PYTHONPATH`.

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

The ESP32 must send two comma-separated readings per line:

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

## Project structure

```text
src/als_monitor/
|-- eye_tracker/
|-- grip_monitor/
`-- shoulder_monitor/
```

This project is a measurement prototype and is not a diagnostic medical device.
