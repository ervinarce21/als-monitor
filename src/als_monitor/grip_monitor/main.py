"""Live two-channel grip-force monitor for an ESP32 serial source."""

import collections
import threading
import time

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import serial


SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200
WINDOW_SECONDS = 10.0
Y_LIMITS = (-500000, 500000)


def read_serial_data(timestamps, left_data, right_data, maximums, data_lock,
                     stop_event):
    """Read `left_grip,right_grip` records until the UI closes."""
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) as connection:
            print("Connected to ESP32 on %s" % SERIAL_PORT)
            while not stop_event.is_set():
                line = connection.readline().decode(
                    "utf-8", errors="ignore").strip()
                if not line:
                    continue
                try:
                    left_value, right_value = map(float, line.split(","))
                except ValueError:
                    continue

                current_time = time.time()
                with data_lock:
                    timestamps.append(current_time)
                    left_data.append(left_value)
                    right_data.append(right_value)
                    if (maximums["left"] is None or
                            left_value > maximums["left"]):
                        maximums["left"] = left_value
                    if (maximums["right"] is None or
                            right_value > maximums["right"]):
                        maximums["right"] = right_value

                    while (timestamps and
                           current_time - timestamps[0] > WINDOW_SECONDS):
                        timestamps.popleft()
                        left_data.popleft()
                        right_data.popleft()
    except (OSError, serial.SerialException) as exc:
        print("Serial connection error: %s" % exc)


def main():
    timestamps = collections.deque()
    left_data = collections.deque()
    right_data = collections.deque()
    maximums = {"left": None, "right": None}
    data_lock = threading.Lock()
    stop_event = threading.Event()

    reader = threading.Thread(
        target=read_serial_data,
        args=(timestamps, left_data, right_data, maximums, data_lock,
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
    axes.set_xlim(-WINDOW_SECONDS, 0)
    axes.set_ylim(*Y_LIMITS)
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
            left_maximum = maximums["left"]
            right_maximum = maximums["right"]

        if time_snapshot:
            now = time.time()
            relative_time = [timestamp - now for timestamp in time_snapshot]
            left_line.set_data(relative_time, left_snapshot)
            right_line.set_data(relative_time, right_snapshot)
        if left_maximum is not None:
            left_max_text.set_text("Left max: %.2f N" % left_maximum)
        if right_maximum is not None:
            right_max_text.set_text("Right max: %.2f N" % right_maximum)
        return left_line, right_line, left_max_text, right_max_text

    graph_animation = animation.FuncAnimation(
        figure, update, interval=50, blit=False, cache_frame_data=False)
    # Retain the animation object until the blocking plot window closes.
    figure._grip_animation = graph_animation

    try:
        plt.show()
    finally:
        stop_event.set()
        reader.join(timeout=1.0)
        if maximums["left"] is not None:
            print("Left maximum grip: %.2f N" % maximums["left"])
        if maximums["right"] is not None:
            print("Right maximum grip: %.2f N" % maximums["right"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
