"""Shoulder elevation and arm-raise velocity monitor."""

import json
import csv
import math
import os
import sqlite3
import time

import cv2
import numpy as np

from .pose import ShoulderPose


DISPLAY_WIDTH = 1024
DISPLAY_HEIGHT = 600
WINDOW_NAME = "NEXA - Upper Limb Motion Analysis"
DATABASE_PATH = "nexa_evaluations.db"


def save_velocity_analysis(output_dir, times, velocities, peak, arm):
    """Save the raw samples and the same smoothed curve used for peak reporting."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "shoulder_velocity.csv"), "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time_seconds", "velocity_deg_per_sec"])
        writer.writerows(zip(times, velocities))
    figure = Figure(figsize=(9, 4.5), tight_layout=True)
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    axes.plot(times, velocities, color="gray", alpha=0.5, label="Raw velocity")
    smoothed = np.convolve(velocities, np.ones(3) / 3, mode="valid")
    axes.plot(times[1:-1], smoothed, color="blue", label="Velocity (3-sample mean)")
    axes.axhline(peak, color="red", linestyle="--", label="Peak: %.2f deg/s" % peak)
    axes.set(title="NEXA: %s Arm Raise Velocity Curve" % arm,
             xlabel="Time (seconds)", ylabel="Angular velocity (deg/s)")
    axes.legend()
    axes.grid(True, alpha=0.3)
    figure.savefig(os.path.join(output_dir, "shoulder_analysis.png"))


def init_db():
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS upper_limb_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id TEXT NOT NULL,
                session_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                evaluated_arm TEXT CHECK(evaluated_arm IN ('LEFT', 'RIGHT')),
                movement_type TEXT DEFAULT 'ARM_RAISE',
                peak_angular_velocity_deg_sec REAL NOT NULL,
                calibration_status TEXT DEFAULT 'PASS'
            )
            """
        )


def save_to_db(participant_id, evaluated_arm, peak_velocity):
    value = round(float(peak_velocity), 2)
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute(
            """
            INSERT INTO upper_limb_records
                (participant_id, evaluated_arm, peak_angular_velocity_deg_sec)
            VALUES (?, ?, ?)
            """,
            (participant_id, evaluated_arm, value),
        )
    print("\n[DATABASE SUCCESS] Saved %.2f deg/s for Participant: %s (%s Arm)"
          % (value, participant_id, evaluated_arm))


def calculate_shoulder_elevation_angle(shoulder_pt, wrist_pt):
    """Return arm elevation relative to downward vertical, in degrees."""
    sx, sy = shoulder_pt
    wx, wy = wrist_pt
    arm_vec = np.array([wx - sx, wy - sy])
    norm_arm = np.linalg.norm(arm_vec)
    if norm_arm == 0:
        return 0.0
    dot_prod = np.dot(arm_vec, np.array([0, 1])) / norm_arm
    return math.degrees(np.arccos(np.clip(dot_prod, -1.0, 1.0)))


def _draw_overlay(frame, participant_id, arm_choice, state, angle,
                  velocity, peak_velocity, remaining):
    cv2.rectangle(frame, (20, 20), (570, 205), (0, 0, 0), -1)
    cv2.rectangle(frame, (20, 20), (570, 205), (255, 255, 255), 2)
    cv2.putText(frame, "NEXA: %s Arm Raise Task" % arm_choice, (40, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(frame, "Participant: %s" % participant_id, (40, 88),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 2)
    cv2.putText(frame, ("Arm Elevation: %d deg" % int(angle)
                        if angle is not None else "Arm not detected"), (40, 125),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)

    if state == "RECORDING":
        cv2.putText(frame, "STATUS: RECORDING (%.1fs)" % remaining,
                    (40, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.75,
                    (0, 0, 255), 2)
        cv2.putText(frame, "Live Velocity: %d deg/s" % int(velocity),
                    (40, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                    (0, 255, 255), 2)
    elif state == "FINISHED":
        cv2.putText(frame, "STATUS: COMPLETE", (40, 160),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)
        cv2.putText(frame, "PEAK VELOCITY: %.1f deg/s" % peak_velocity,
                    (40, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.75,
                    (0, 255, 255), 2)
    elif state == "WAITING":
        cv2.putText(frame, "START REQUESTED: waiting for arm", (40, 165),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2)
    else:
        cv2.putText(frame, "STATUS: READY (Press SPACE to Start)",
                    (40, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                    (255, 255, 0), 2)


def main():
    init_db()
    print("NEXA UPPER-LIMB MOTION ANALYSIS MODULE")
    integrated_run = bool(os.environ.get("NEXA_OUTPUT_DIR"))
    if integrated_run:
        participant_id = os.environ.get("NEXA_PARTICIPANT_ID", "NEXA-001")
        arm_choice = os.environ.get("NEXA_EVALUATED_ARM", "RIGHT").upper()
    else:
        participant_id = input(
            "Enter Participant ID (e.g., NEXA-001): ").strip()
        participant_id = participant_id or "NEXA-001"
        arm_choice = input(
            "Select arm to evaluate (RIGHT / LEFT): ").strip().upper()
    if arm_choice not in ("RIGHT", "LEFT"):
        arm_choice = "RIGHT"

    try:
        pose = ShoulderPose()
    except Exception as exc:
        print("[ERROR] Pose tracking unavailable: %s" % exc)
        print("Install mediapipe in the NEXA Python environment and the pose model (README).")
        return 2
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Could not open camera. Check USB webcam connection.")
        pose.close()
        return 2

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, DISPLAY_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, DISPLAY_HEIGHT)
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, DISPLAY_WIDTH, DISPLAY_HEIGHT)
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN,
                          cv2.WINDOW_FULLSCREEN)

    prev_angle = None
    prev_time = None
    velocity_buffer = []
    velocity_times = []
    state = "READY"
    start_time = 0.0
    trial_duration = 5.0
    peak_velocity = 0.0
    finished_at = None
    start_clicked = [False]
    start_bounds = (DISPLAY_WIDTH - 200, 25, DISPLAY_WIDTH - 20, 85)

    def on_mouse(event, x, y, flags, param):
        x1, y1, x2, y2 = start_bounds
        if event == cv2.EVENT_LBUTTONUP and x1 <= x <= x2 and y1 <= y <= y2:
            start_clicked[0] = True

    cv2.setMouseCallback(WINDOW_NAME, on_mouse)
    print("Click Start or focus the camera window and press SPACE. "
          "The selected shoulder and wrist must be visible.", flush=True)

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Video frame drop detected.")
                break

            frame = cv2.resize(frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT),
                               interpolation=cv2.INTER_AREA)
            h, w = frame.shape[:2]
            current_time = time.monotonic()
            points = pose.detect(frame, current_time)
            # Mirror only the display, preserving anatomical landmark labels.
            frame = cv2.flip(frame, 1)
            points = {name: (w - 1 - x, y) for name, (x, y) in points.items()}
            for side, color in (("LEFT", (255, 180, 0)), ("RIGHT", (0, 180, 255))):
                point = points.get(side + "_SHOULDER")
                if point is not None:
                    cv2.circle(frame, point, 8, color, -1)
                    cv2.putText(frame, side, (max(0, point[0] - 30), point[1] + 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            shoulder_pt = points.get(arm_choice + "_SHOULDER")
            wrist_pt = points.get(arm_choice + "_WRIST")
            tracked = shoulder_pt is not None and wrist_pt is not None
            if state == "WAITING" and tracked:
                velocity_buffer = []
                velocity_times = []
                prev_angle = prev_time = None
                start_time = current_time
                finished_at = None
                state = "RECORDING"
                print("[START] Recording %s arm for %.1f seconds." %
                      (arm_choice, trial_duration), flush=True)
            angle = (calculate_shoulder_elevation_angle(shoulder_pt, wrist_pt)
                     if tracked else None)
            velocity = 0.0
            valid_velocity = tracked and prev_angle is not None and prev_time is not None
            if valid_velocity:
                delta_time = current_time - prev_time
                if delta_time > 0:
                    velocity = abs(angle - prev_angle) / delta_time
            prev_angle, prev_time = angle, current_time

            remaining = trial_duration
            if state == "RECORDING":
                elapsed = current_time - start_time
                remaining = max(0.0, trial_duration - elapsed)
                if valid_velocity:
                    velocity_buffer.append(velocity)
                    velocity_times.append(elapsed)
                if elapsed >= trial_duration:
                    if len(velocity_buffer) < 3:
                        print("[ERROR] Insufficient tracked frames. Repeat with shoulder and wrist visible.")
                        return 2
                    if len(velocity_buffer) >= 3:
                        smoothed = np.convolve(
                            velocity_buffer, np.ones(3) / 3, mode="valid")
                        peak_velocity = float(np.max(smoothed))
                    else:
                        peak_velocity = max(velocity_buffer, default=0.0)
                    save_to_db(participant_id, arm_choice, peak_velocity)
                    output_dir = os.environ.get("NEXA_OUTPUT_DIR")
                    analysis_dir = output_dir or os.path.join(
                        "data", "shoulder_monitor", time.strftime("%Y%m%d_%H%M%S"))
                    save_velocity_analysis(analysis_dir, velocity_times, velocity_buffer,
                                           peak_velocity, arm_choice)
                    print("[ANALYSIS] Saved velocity plot and samples: %s" % analysis_dir)
                    if output_dir:
                        os.makedirs(output_dir, exist_ok=True)
                        with open(os.path.join(
                                output_dir, "shoulder_summary.json"), "w") as handle:
                            json.dump({
                                "peak_velocity": peak_velocity,
                                "evaluated_arm": arm_choice,
                                "participant_id": participant_id,
                                "tracking_method": "mediapipe_pose",
                                "valid_velocity_samples": len(velocity_buffer),
                            }, handle, indent=2)
                    state = "FINISHED"
                    finished_at = current_time

            if tracked:
                cv2.circle(frame, wrist_pt, 10, (0, 255, 0), -1)
                cv2.line(frame, shoulder_pt, wrist_pt, (255, 255, 0), 3)
            cv2.putText(frame, "L: left arm   R: right arm   SPACE: start   Q: exit",
                        (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            _draw_overlay(frame, participant_id, arm_choice, state, angle,
                          velocity, peak_velocity, remaining)
            if not tracked:
                missing = []
                if shoulder_pt is None:
                    missing.append("shoulder")
                if wrist_pt is None:
                    missing.append("wrist")
                cv2.putText(frame, "Keep %s %s in view" %
                            (arm_choice, " and ".join(missing)), (30, h - 55),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
            x1, y1, x2, y2 = start_bounds
            cv2.rectangle(frame, (x1, y1), (x2, y2), (70, 70, 70), -1)
            cv2.putText(frame, "Recording" if state == "RECORDING" else
                        "Cancel start" if state == "WAITING" else "Start",
                        (x1 + 10, y1 + 38), cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, (255, 255, 255), 2)
            cv2.imshow(WINDOW_NAME, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("l"), ord("r"), ord("L"), ord("R")) and state in ("READY", "WAITING"):
                arm_choice = "LEFT" if key in (ord("l"), ord("L")) else "RIGHT"
                prev_angle = prev_time = None
            requested = key == 32 or start_clicked[0]
            start_clicked[0] = False
            if requested and state != "RECORDING":
                state = "READY" if state == "WAITING" else "WAITING"
                print("[START] %s" % ("Cancelled." if state == "READY" else
                      "Requested; recording begins when the selected arm is detected."), flush=True)
            elif key == ord("q"):
                break

            # NEXA owns the workflow during an integrated run. Once the result
            # is safely written, briefly show COMPLETE and return control to
            # the NEXA review screen with a successful process exit.
            if (integrated_run and state == "FINISHED" and
                    finished_at is not None and
                    current_time - finished_at >= 1.0):
                print("[COMPLETE] Returning result to NEXA UI.")
                break
    finally:
        pose.close()
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
