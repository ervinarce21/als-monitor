"""
OV9281 / Raspberry Pi camera access (Picamera2 + libcamera).

Returns grayscale frames with a monotonic timestamp on the SAME clock as
time.perf_counter(), so frame times and target-onset times are comparable.
"""

import time

import numpy as np

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
    _PICAMERA2_IMPORT_ERROR = None
except Exception as exc:          # pragma: no cover - depends on host
    PICAMERA2_AVAILABLE = False
    _PICAMERA2_IMPORT_ERROR = exc

import config


class CameraError(RuntimeError):
    """Raised for any camera initialisation or capture failure."""


def _clock_offset():
    """
    Offset that converts a libcamera SensorTimestamp (CLOCK_BOOTTIME, ns)
    into the time.perf_counter() timebase.

        perf_time = boottime_seconds + offset
    """
    try:
        boot = time.clock_gettime(time.CLOCK_BOOTTIME)
    except (AttributeError, OSError):
        return None
    return time.perf_counter() - boot


class IRCamera:
    """Thin, blocking wrapper around one Picamera2 instance."""

    def __init__(self):
        self.picam2 = None
        self._offset = None
        self._format = config.CAMERA_FORMAT
        self._warned_timestamp = False
        self.width = config.CAMERA_WIDTH
        self.height = config.CAMERA_HEIGHT

    # ------------------------------------------------------------------
    def start(self):
        if not PICAMERA2_AVAILABLE:
            raise CameraError(
                "Picamera2 is not available (%s). Install python3-picamera2."
                % _PICAMERA2_IMPORT_ERROR
            )
        try:
            self.picam2 = Picamera2()
        except Exception as exc:
            raise CameraError("Could not open the camera: %s" % exc)

        try:
            cfg = self.picam2.create_video_configuration(
                main={"size": (config.CAMERA_WIDTH, config.CAMERA_HEIGHT),
                      "format": self._format},
                buffer_count=6,
                queue=False,          # always hand us the newest frame
            )
            cfg["transform"] = self._transform()
            self.picam2.configure(cfg)
        except Exception as exc:
            # Fall back to the most portable format if the requested one
            # is not supported by this sensor/libcamera build.
            if self._format != "YUV420":
                self._format = "YUV420"
                cfg = self.picam2.create_video_configuration(
                    main={"size": (config.CAMERA_WIDTH, config.CAMERA_HEIGHT),
                          "format": self._format},
                    buffer_count=6,
                    queue=False,
                )
                cfg["transform"] = self._transform()
                self.picam2.configure(cfg)
            else:
                raise CameraError("Camera configuration failed: %s" % exc)

        self._apply_controls()

        try:
            self.picam2.start()
        except Exception as exc:
            raise CameraError("Camera failed to start: %s" % exc)

        self._offset = _clock_offset()
        time.sleep(config.CAMERA_WARMUP_S)

        # Confirm the real stream geometry (libcamera may align the width).
        try:
            stream_cfg = self.picam2.camera_configuration()["main"]
            self.width, self.height = stream_cfg["size"]
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _transform(self):
        try:
            from libcamera import Transform
            return Transform(hflip=int(config.CAMERA_HFLIP),
                             vflip=int(config.CAMERA_VFLIP))
        except Exception:
            return None

    def _apply_controls(self):
        """Frame rate plus manual exposure/gain (best effort)."""
        ctrls = {}
        if config.CAMERA_FPS > 0:
            dur = int(1_000_000 / config.CAMERA_FPS)
            ctrls["FrameDurationLimits"] = (dur, dur)
        if config.CAMERA_MANUAL_EXPOSURE:
            ctrls["AeEnable"] = False
            ctrls["ExposureTime"] = int(config.CAMERA_EXPOSURE_US)
            ctrls["AnalogueGain"] = float(config.CAMERA_ANALOGUE_GAIN)
        for key, value in list(ctrls.items()):
            try:
                self.picam2.set_controls({key: value})
            except Exception:
                # Not every control exists on every sensor/driver combination.
                ctrls.pop(key, None)

    # ------------------------------------------------------------------
    def capture(self):
        """
        Grab one frame.

        Returns (timestamp_perf_counter_seconds, grayscale_uint8_array).
        Raises CameraError on an unrecoverable capture failure.
        """
        if self.picam2 is None:
            raise CameraError("capture() called before start()")

        try:
            request = self.picam2.capture_request()
        except Exception as exc:
            raise CameraError("Frame capture failed: %s" % exc)

        try:
            array = request.make_array("main")
            metadata = request.get_metadata()
        finally:
            request.release()

        recv_time = time.perf_counter()
        timestamp = self._frame_timestamp(metadata, recv_time)
        return timestamp, self._to_gray(array)

    def _frame_timestamp(self, metadata, recv_time):
        if config.CAMERA_USE_SENSOR_TIMESTAMP and self._offset is not None:
            sensor_ns = metadata.get("SensorTimestamp")
            if sensor_ns:
                ts = sensor_ns / 1e9 + self._offset
                # Sanity: must be in the recent past relative to reception.
                if -0.001 <= (recv_time - ts) <= 0.5:
                    return ts
                if not self._warned_timestamp:
                    print("[camera] SensorTimestamp out of range, "
                          "using receive time instead.")
                    self._warned_timestamp = True
        return recv_time

    def _to_gray(self, array):
        """Extract a single-channel uint8 image from whatever we were given."""
        if array.ndim == 2:
            # YUV420 arrives as (H*3/2, W); the first H rows are the Y plane.
            if array.shape[0] >= self.height * 3 // 2 and self._format == "YUV420":
                return np.ascontiguousarray(array[: self.height, : self.width])
            return array
        if array.ndim == 3:
            # RGB888/BGR888 or XBGR8888 - the mono sensor replicates channels.
            return np.ascontiguousarray(array[:, :, 0])
        raise CameraError("Unexpected frame shape %s" % (array.shape,))

    # ------------------------------------------------------------------
    def stop(self):
        if self.picam2 is not None:
            try:
                self.picam2.stop()
            except Exception:
                pass
            try:
                self.picam2.close()
            except Exception:
                pass
            self.picam2 = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False