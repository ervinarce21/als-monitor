"""Capture per-hand load-cell calibration from the ESP32 serial stream."""

import json
import math
import os
import statistics
import time

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QComboBox, QDoubleSpinBox, QMessageBox)

import config


class GripCalibrationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grip calibration")
        self.resize(620, 440)
        self.connection = None
        self.buffer = b""
        self.samples = None
        self.zeros = {}
        self.calibrations = {}
        self.testing = False
        layout = QVBoxLayout(self)
        instructions = QLabel(
            "Close any running grip assessment. Capture each unloaded sensor, "
            "then apply a known load in the same direction as a grip squeeze "
            "and capture the loaded sensor. Keep the load steady during capture.")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        row = QHBoxLayout()
        self.side = QComboBox()
        self.side.addItems(["Left", "Right"])
        row.addWidget(self.side)
        row.addWidget(QLabel("Calibration mass (kg)"))
        self.mass = QDoubleSpinBox()
        self.mass.setRange(0.001, 1000)
        self.mass.setDecimals(3)
        self.mass.setValue(2)
        row.addWidget(self.mass)
        layout.addLayout(row)
        self.status = QLabel("Ready. Each capture averages 50 fresh readings.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.results = QLabel("Left: pending\nRight: pending")
        self.results.setWordWrap(True)
        layout.addWidget(self.results)
        self.zero_btn = QPushButton("Capture unloaded")
        self.load_btn = QPushButton("Capture known load")
        self.zero_btn.clicked.connect(lambda: self.capture(False))
        self.load_btn.clicked.connect(lambda: self.capture(True))
        layout.addWidget(self.zero_btn)
        layout.addWidget(self.load_btn)
        self.test_btn = QPushButton("Test calibration")
        self.test_btn.clicked.connect(self.test_calibration)
        layout.addWidget(self.test_btn)
        self.save_btn = QPushButton("Save calibrated hands")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        layout.addWidget(self.save_btn)
        close = QPushButton("Cancel")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.poll)
        self.finished.connect(self.cleanup)

    def capture(self, loaded, testing=False):
        side = self.side.currentText().lower()
        if loaded and not testing and side not in self.zeros:
            self.status.setText("Capture the unloaded sensor first.")
            return
        try:
            import serial
            if self.connection is None:
                self.connection = serial.Serial("/dev/ttyUSB0", 115200, timeout=0)
            self.connection.reset_input_buffer()
        except Exception as exc:
            self.status.setText(f"Cannot read grip controller: {exc}")
            return
        self.buffer = b""
        self.testing = testing
        self.samples = []
        self.capture_side, self.loaded = side, loaded
        self.capture_mass = self.mass.value()
        # Allow the ESP32 to settle after opening/resetting its serial port.
        self.ready_at = time.monotonic() + 2
        self.deadline = self.ready_at + 15
        for widget in (self.side, self.mass, self.zero_btn, self.load_btn, self.save_btn):
            widget.setEnabled(False)
        self.test_btn.setEnabled(testing)
        self.test_btn.setText("Stop test" if testing else "Test calibration")
        self.status.setText("Settling sensor...")
        self.timer.start()

    def poll(self):
        try:
            data = self.connection.read(min(self.connection.in_waiting, 8192))
            if time.monotonic() < self.ready_at:
                return
            self.buffer += data
            while b"\n" in self.buffer and (self.testing or len(self.samples) < 50):
                line, self.buffer = self.buffer.split(b"\n", 1)
                try:
                    right, left = map(float, line.decode("ascii").strip().split(","))
                except (ValueError, UnicodeError):
                    continue
                if not (math.isfinite(left) and math.isfinite(right)):
                    continue
                raw = left if self.capture_side == "left" else right
                if self.testing:
                    c = self.test_values
                    force = abs((raw - c["zero_counts"]) * c["mass_kg"] *
                                9.80665 / c["delta_counts"] * c["polarity"])
                    expected = self.capture_mass * 9.80665
                    self.status.setText(
                        f"{self.capture_side.title()}: {force:.2f} N | "
                        f"Expected: {expected:.2f} N | Difference: {force - expected:+.2f} N")
                    self.deadline = time.monotonic() + 15
                else:
                    self.samples.append(raw)
            if len(self.buffer) > 8192:
                self.buffer = b""
            if self.testing:
                if time.monotonic() > self.deadline:
                    raise RuntimeError("No valid grip readings received for 15 seconds.")
                return
            self.status.setText(f"Capturing {self.capture_side}: {len(self.samples)}/50")
            if len(self.samples) == 50:
                self.finish_capture()
            elif time.monotonic() > self.deadline:
                raise RuntimeError("Timed out waiting for 50 valid right,left readings.")
        except Exception as exc:
            self.stop_capture()
            self.status.setText(f"Capture failed: {exc}")

    def stop_capture(self):
        self.timer.stop()
        self.testing = False
        self.test_btn.setText("Test calibration")
        self.test_btn.setEnabled(True)
        for widget in (self.side, self.mass, self.zero_btn, self.load_btn):
            widget.setEnabled(True)
        self.save_btn.setEnabled(bool(self.calibrations))

    def test_calibration(self):
        if self.testing:
            self.stop_capture()
            return
        side = self.side.currentText().lower()
        try:
            values = self.calibrations.get(side)
            if values is None:
                if side in self.zeros:
                    raise ValueError("Capture the known load to complete this calibration first.")
                with open(os.path.join(config.DATA_DIR, "grip_calibration.json"),
                          encoding="utf-8") as handle:
                    values = json.load(handle).get(side)
            if not values:
                raise ValueError("Calibrate this hand first.")
            values = {key: float(values[key]) for key in
                      ("zero_counts", "delta_counts", "mass_kg", "polarity")}
            if (not all(math.isfinite(v) for v in values.values()) or
                    values["delta_counts"] == 0 or values["mass_kg"] <= 0 or
                    values["polarity"] not in (-1, 1)):
                raise ValueError("Invalid calibration values.")
            self.test_values = values
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            self.status.setText(f"Cannot test: {exc}")
            return
        self.capture(True, testing=True)

    def finish_capture(self):
        mean = statistics.mean(self.samples)
        side = self.capture_side
        if self.loaded:
            delta = mean - self.zeros[side]
            if abs(delta) <= max(1, 5 * statistics.pstdev(self.samples)):
                raise ValueError("Load change is too small or unstable. Reposition and retry.")
            self.calibrations[side] = {
                "zero_counts": self.zeros[side], "delta_counts": delta,
                "mass_kg": self.capture_mass, "polarity": 1.0,
            }
        else:
            self.zeros[side] = mean
            self.calibrations.pop(side, None)
        self.stop_capture()
        self.status.setText(f"Captured {side}: {mean:.1f} counts")
        self.results.setText("\n".join(
            f"{hand.title()}: " + (
                f"calibrated, {self.calibrations[hand]['mass_kg']:g} kg"
                if hand in self.calibrations else
                "unloaded captured" if hand in self.zeros else "pending")
            for hand in ("left", "right")))

    def save(self):
        if not self.calibrations:
            return
        path = os.path.join(config.DATA_DIR, "grip_calibration.json")
        try:
            config.ensure_dirs()
            saved = {}
            if os.path.exists(path):
                with open(path, encoding="utf-8") as handle:
                    saved = json.load(handle)
                if not isinstance(saved, dict):
                    raise ValueError("Existing calibration file is not an object.")
            saved.update(self.calibrations)
            with open(path + ".tmp", "w", encoding="utf-8") as handle:
                json.dump(saved, handle, indent=2, allow_nan=False)
            os.replace(path + ".tmp", path)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Calibration save failed", str(exc))
            return
        QMessageBox.information(self, "Calibration saved",
                                "Saved: " + ", ".join(self.calibrations))
        self.accept()

    def cleanup(self, _result):
        self.timer.stop()
        if self.connection is not None:
            self.connection.close()
            self.connection = None
