"""Shoulder elevation and arm-raise velocity monitor."""

import json
import math
import os
import sqlite3
import time

import cv2
import numpy as np


DISPLAY_WIDTH = 1024
DISPLAY_HEIGHT = 600
WINDOW_NAME = "NEXA - Upper Limb Motion Analysis"
DATABASE_PATH = "nexa_evaluations.db"


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
    cv2.putText(frame, "Arm Elevation: %d deg" % int(angle), (40, 125),
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

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Could not open camera. Check USB webcam connection.")
        return 2

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, DISPLAY_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, DISPLAY_HEIGHT)
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, DISPLAY_WIDTH, DISPLAY_HEIGHT)
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN,
                          cv2.WINDOW_FULLSCREEN)

    bg_sub = cv2.createBackgroundSubtractorMOG2(
        history=500, varThreshold=50, detectShadows=False)
    prev_angle = None
    prev_time = None
    velocity_buffer = []
    state = "READY"
    start_time = 0.0
    trial_duration = 5.0
    peak_velocity = 0.0
    finished_at = None

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Video frame drop detected.")
                break

            frame = cv2.flip(frame, 1)
            frame = cv2.resize(frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT),
                               interpolation=cv2.INTER_AREA)
            h, w = frame.shape[:2]
            current_time = time.time()
            shoulder_x = 0.35 if arm_choice == "RIGHT" else 0.65
            shoulder_pt = (int(w * shoulder_x), int(h * 0.40))
            wrist_pt = (shoulder_pt[0], shoulder_pt[1] + 150)

            mask = bg_sub.apply(frame)
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                contour = max(contours, key=cv2.contourArea)
                if cv2.contourArea(contour) > 1000:
                    moments = cv2.moments(contour)
                    if moments["m00"]:
                        wrist_pt = (int(moments["m10"] / moments["m00"]),
                                    int(moments["m01"] / moments["m00"]))

            angle = calculate_shoulder_elevation_angle(shoulder_pt, wrist_pt)
            velocity = 0.0
            if prev_angle is not None and prev_time is not None:
                delta_time = current_time - prev_time
                if delta_time > 0:
                    velocity = abs(angle - prev_angle) / delta_time
            prev_angle, prev_time = angle, current_time

            remaining = trial_duration
            if state == "RECORDING":
                elapsed = current_time - start_time
                remaining = max(0.0, trial_duration - elapsed)
                velocity_buffer.append(velocity)
                if elapsed >= trial_duration:
                    if len(velocity_buffer) >= 3:
                        smoothed = np.convolve(
                            velocity_buffer, np.ones(3) / 3, mode="valid")
                        peak_velocity = float(np.max(smoothed))
                    else:
                        peak_velocity = max(velocity_buffer, default=0.0)
                    save_to_db(participant_id, arm_choice, peak_velocity)
                    output_dir = os.environ.get("NEXA_OUTPUT_DIR")
                    if output_dir:
                        os.makedirs(output_dir, exist_ok=True)
                        with open(os.path.join(
                                output_dir, "shoulder_summary.json"), "w") as handle:
                            json.dump({
                                "peak_velocity": peak_velocity,
                                "evaluated_arm": arm_choice,
                                "participant_id": participant_id,
                            }, handle, indent=2)
                    state = "FINISHED"
                    finished_at = current_time

            cv2.circle(frame, shoulder_pt, 10, (0, 0, 255), -1)
            cv2.circle(frame, wrist_pt, 10, (0, 255, 0), -1)
            cv2.line(frame, shoulder_pt, wrist_pt, (255, 255, 0), 3)
            _draw_overlay(frame, participant_id, arm_choice, state, angle,
                          velocity, peak_velocity, remaining)
            cv2.imshow(WINDOW_NAME, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == 32 and state != "RECORDING":
                velocity_buffer = []
                start_time = time.time()
                state = "RECORDING"
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
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
