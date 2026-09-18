#!/usr/bin/env python3
"""
Setup helper (run before testing, not part of a session).

Shows the live IR image with the detected pupil marked, so you can check
camera framing, exposure and the DIR_SIGN_X / DIR_SIGN_Y settings in
config.py. Press Q or ESC to quit, B to toggle the binary mask.
"""

import math
import sys
import time

import cv2

from . import config
from .camera import CameraError, create_camera, configure_camera
from .face_tracker import create_tracker


def main(argv=None):
    configure_camera(argv, module="als_monitor.eye_tracker.preview")
    config.DEBUG_PREVIEW = True
    camera = create_camera()
    tracker = None

    try:
        tracker = create_tracker()
        camera.start()
    except Exception as exc:
        print("[fatal] %s" % exc)
        camera.stop()
        if tracker is not None and hasattr(tracker, "close"):
            tracker.close()
        return 2

    show_mask = False
    last = time.perf_counter()
    fps = 0.0

    try:
        while True:
            try:
                timestamp, gray = camera.capture()
            except CameraError as exc:
                print("[fatal] %s" % exc)
                return 2

            sample = tracker.detect(gray, timestamp)
            now = time.perf_counter()
            dt = now - last
            last = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 / dt

            if show_mask and tracker.last_debug is not None:
                view = cv2.cvtColor(tracker.last_debug, cv2.COLOR_GRAY2BGR)
            else:
                view = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

            if sample.found and not math.isnan(sample.x):
                centre = (int(sample.x), int(sample.y))
                cv2.circle(view, centre, max(3, int(sample.radius)),
                           (0, 255, 0), 2)
                cv2.drawMarker(view, centre, (0, 0, 255),
                               cv2.MARKER_CROSS, 12, 1)
                label = "x=%.1f y=%.1f c=%.2f" % (sample.x, sample.y,
                                                  sample.confidence)
            else:
                label = "no pupil"

            cv2.putText(view, "%s | %.0f fps" % (label, fps), (8, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            cv2.imshow("NEXA pupil preview", view)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("b"):
                show_mask = not show_mask
    finally:
        camera.stop()
        if tracker is not None and hasattr(tracker, "close"):
            tracker.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
