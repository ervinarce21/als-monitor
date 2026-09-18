"""Live two-channel grip-force monitor for an ESP32 serial source."""

import collections
import json
import math
import os
import threading
import time

import matplotlib

# Use Tk for the standalone graph. The Qt backend requests window activation,
# which Wayland intentionally does not support and reports as a warning.
matplotlib.use("TkAgg")

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import serial


SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200
WINDOW_SECONDS = 10.0
INITIAL_Y_LIMITS = (-10.0, 10.0)

# ESP32 sends raw counts in right,left order. Calibrated with a 2 kg load.
CALIBRATION = {
    "left": {"zero_counts": -114000.0, "delta_counts": 63000.0, "mass_kg": 2.0},
    "right": {"zero_counts": 59500.0, "delta_counts": -39200.0, "mass_kg": 2.0},
}


def force_newtons(raw_counts, side):
    calibration = CALIBRATION[side]
    scale = (calibration["mass_kg"] * 9.80665 /
             calibration["delta_counts"])
    return (raw_counts - calibration["zero_counts"]) * scale


def format_duration(seconds):
    """Format elapsed seconds as MM:SS.s."""
    minutes, remaining = divmod(max(0.0, seconds), 60.0)
    return "%02d:%04.1f" % (int(minutes), remaining)


def read_serial_data(timestamps, left_data, right_data, session, data_lock,
                     stop_event):
    """Read `right_grip,left_grip` records until the UI closes."""
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) as connection:
            print("Connected to ESP32 on %s" % SERIAL_PORT)
            with data_lock:
                session["status"] = "Connected - waiting for readings"
            while not stop_event.is_set():
                line = connection.readline().decode(
                    "utf-8", errors="ignore").strip()
                if not line:
                    continue
                try:
                    right_value, left_value = map(float, line.split(","))
                except ValueError:
                    continue
                if not (math.isfinite(right_value) and math.isfinite(left_value)):
                    continue
                right_value = force_newtons(right_value, "right")
                left_value = force_newtons(left_value, "left")

                current_time = time.time()
                with data_lock:
                    session["status"] = "Receiving data"
                    if session["started_at"] is None:
                        session["started_at"] = time.monotonic()
                    timestamps.append(current_time)
                    left_data.append(left_value)
                    right_data.append(right_value)
                    if (session["left_max"] is None or
                            left_value > session["left_max"]):
                        session["left_max"] = left_value
                    if (session["right_max"] is None or
                            right_value > session["right_max"]):
                        session["right_max"] = right_value

                    while (timestamps and
                           current_time - timestamps[0] > WINDOW_SECONDS):
                        timestamps.popleft()
                        left_data.popleft()
                        right_data.popleft()
    except (OSError, serial.SerialException) as exc:
        with data_lock:
            session["status"] = "Serial error: %s" % exc
        print("Serial connection error: %s" % exc)


def main():
    timestamps = collections.deque()
    left_data = collections.deque()
    right_data = collections.deque()
    session = {
        "left_max": None,
        "right_max": None,
        "started_at": None,
        "status": "Opening %s..." % SERIAL_PORT,
    }
    data_lock = threading.Lock()
    stop_event = threading.Event()

    reader = threading.Thread(
        target=read_serial_data,
        args=(timestamps, left_data, right_data, session, data_lock,
              stop_event),
        daemon=True,
    )
    reader.start()

    figure, axes = plt.subplots()
    left_line, = axes.plot([], [], label="Left Grip", color="blue",
                           linewidth=1.5)
    right_line, = axes.plot([], [], label="Right Grip", color="orange",
                            linewidth=1.5)
    left_max_text = axes.text(
        0.98, 0.96, "Left max: -- N", color="blue",
        ha="right", va="top", transform=axes.transAxes)
    right_max_text = axes.text(
        0.98, 0.90, "Right max: -- N", color="darkorange",
        ha="right", va="top", transform=axes.transAxes)
    duration_text = axes.text(
        0.98, 0.84, "Duration: 00:00.0", color="black",
        ha="right", va="top", transform=axes.transAxes)
    status_text = axes.text(
        0.02, 0.04, session["status"], color="dimgray",
        ha="left", va="bottom", transform=axes.transAxes)
    axes.set_xlim(-WINDOW_SECONDS, 0)
    axes.set_ylim(*INITIAL_Y_LIMITS)
    axes.set_autoscaley_on(False)
    axes.set_autoscalex_on(False)
    axes.legend(loc="upper left")
    axes.set_title("Grip Strength")
    axes.set_xlabel("Seconds Ago")
    axes.set_ylabel("Force (N)")

    def update(_frame):
        with data_lock:
            time_snapshot = list(timestamps)
            left_snapshot = list(left_data)
            right_snapshot = list(right_data)
            left_maximum = session["left_max"]
            right_maximum = session["right_max"]
            started_at = session["started_at"]
            serial_status = session["status"]

        if time_snapshot:
            now = time.time()
            relative_time = [timestamp - now for timestamp in time_snapshot]
            left_line.set_data(relative_time, left_snapshot)
            right_line.set_data(relative_time, right_snapshot)

            visible_values = left_snapshot + right_snapshot
            low = min(visible_values)
            high = max(visible_values)
            span = high - low
            padding = max(span * 0.15, max(abs(low), abs(high)) * 0.05, 1.0)
            axes.set_ylim(min(0.0, low - padding),
                          max(0.0, high + padding))
        if left_maximum is not None:
            left_max_text.set_text("Left max: %.2f N" % left_maximum)
        if right_maximum is not None:
            right_max_text.set_text("Right max: %.2f N" % right_maximum)
        if started_at is not None:
            duration_text.set_text(
                "Duration: %s" % format_duration(time.monotonic() - started_at))
        status_text.set_text(serial_status)
        status_text.set_color(
            "firebrick" if serial_status.startswith("Serial error")
            else "dimgray")
        return (left_line, right_line, left_max_text, right_max_text,
                duration_text, status_text)

    graph_animation = animation.FuncAnimation(
        figure, update, interval=50, blit=False, cache_frame_data=False)
    # Retain the animation object until the blocking plot window closes.
    figure._grip_animation = graph_animation

    try:
        plt.show()
    finally:
        stop_event.set()
        reader.join(timeout=1.0)
        if session["left_max"] is not None:
            print("Left maximum grip: %.2f N" % session["left_max"])
        if session["right_max"] is not None:
            print("Right maximum grip: %.2f N" % session["right_max"])
        if session["started_at"] is not None:
            elapsed = time.monotonic() - session["started_at"]
            print("Session duration: %s" % format_duration(elapsed))
        else:
            elapsed = 0.0
        output_dir = os.environ.get("NEXA_OUTPUT_DIR")
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            with open(os.path.join(output_dir, "grip_summary.json"), "w") as handle:
                json.dump({
                    "peak_left": session["left_max"],
                    "peak_right": session["right_max"],
                    "duration": elapsed,
                    "force_unit": "N",
                    "calibration": CALIBRATION,
                }, handle, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
