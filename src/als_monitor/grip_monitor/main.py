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


def read_serial_data(timestamps, channel_1, channel_2, stop_event):
    """Read `load_cell_1,load_cell_2` records until the UI closes."""
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) as connection:
            print("Connected to ESP32 on %s" % SERIAL_PORT)
            while not stop_event.is_set():
                line = connection.readline().decode(
                    "utf-8", errors="ignore").strip()
                if not line:
                    continue
                try:
                    value_1, value_2 = map(float, line.split(","))
                except ValueError:
                    continue

                current_time = time.time()
                timestamps.append(current_time)
                channel_1.append(value_1)
                channel_2.append(value_2)
                while (timestamps and
                       current_time - timestamps[0] > WINDOW_SECONDS):
                    timestamps.popleft()
                    channel_1.popleft()
                    channel_2.popleft()
    except (OSError, serial.SerialException) as exc:
        print("Serial connection error: %s" % exc)


def main():
    timestamps = collections.deque()
    channel_1 = collections.deque()
    channel_2 = collections.deque()
    stop_event = threading.Event()

    reader = threading.Thread(
        target=read_serial_data,
        args=(timestamps, channel_1, channel_2, stop_event),
        daemon=True,
    )
    reader.start()

    figure, axes = plt.subplots()
    line_1, = axes.plot([], [], label="Load Cell 1", color="blue",
                        linewidth=1.5)
    line_2, = axes.plot([], [], label="Load Cell 2", color="orange",
                        linewidth=1.5)
    axes.set_xlim(-WINDOW_SECONDS, 0)
    axes.set_ylim(*Y_LIMITS)
    axes.set_autoscaley_on(False)
    axes.set_autoscalex_on(False)
    axes.legend(loc="upper left")
    axes.set_title("Grip Strength")
    axes.set_xlabel("Seconds Ago")
    axes.set_ylabel("Force (N)")

    def update(_frame):
        if timestamps:
            now = time.time()
            relative_time = [timestamp - now for timestamp in timestamps]
            line_1.set_data(relative_time, list(channel_1))
            line_2.set_data(relative_time, list(channel_2))
        return line_1, line_2

    graph_animation = animation.FuncAnimation(
        figure, update, interval=50, blit=False, cache_frame_data=False)
    # Retain the animation object until the blocking plot window closes.
    figure._grip_animation = graph_animation

    try:
        plt.show()
    finally:
        stop_event.set()
        reader.join(timeout=1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

