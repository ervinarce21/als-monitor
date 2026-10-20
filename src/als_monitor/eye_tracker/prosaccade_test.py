"""
Visually guided prosaccade task: fullscreen presentation + trial loop.

Timing reference for the WHOLE program is time.perf_counter().
Camera frame timestamps are converted to that same clock in camera.py.
"""

import math
import random
import time

import numpy as np
import pygame

from . import config
from .face_tracker import webcam_position_guidance
from .results import TrialResult
from .saccade_detector import detect_saccade


class AbortTest(Exception):
    """Raised when the operator/participant quits with ESC or Q."""


class ProsaccadeTest:
    def __init__(self, sampler):
        self.sampler = sampler
        self.screen = None
        self.font = None
        self.small_font = None
        self.width = config.SCREEN_WIDTH
        self.height = config.SCREEN_HEIGHT
        self.centre = (self.width // 2, self.height // 2)
        self.baseline = None          # (x, y, noise_px) from calibration
        self.rng = random.Random(config.RANDOM_SEED)
        self._preview_last_update = 0.0

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------
    def init_display(self):
        pygame.init()
        pygame.mouse.set_visible(False)
        flags = pygame.FULLSCREEN if config.FULLSCREEN else 0
        if config.DISPLAY_VSYNC:
            # pygame only honors vsync requests for SCALED or OPENGL displays.
            # SCALED preserves the existing software Surface drawing API.
            try:
                self.screen = pygame.display.set_mode(
                    (self.width, self.height), flags | pygame.SCALED, vsync=1)
                print("[display] Driver %s; vsync requested" %
                      pygame.display.get_driver(), flush=True)
            except (TypeError, pygame.error) as exc:
                print("[display] Vsync unavailable (%s); using standard display" %
                      exc, flush=True)
                self.screen = pygame.display.set_mode(
                    (self.width, self.height), flags)
        else:
            self.screen = pygame.display.set_mode((self.width, self.height), flags)
        pygame.display.set_caption("NEXA - prosaccade latency")
        # Actual surface size wins (fullscreen may be forced to panel size).
        self.width, self.height = self.screen.get_size()
        self.centre = (self.width // 2, self.height // 2)
        self.font = pygame.font.SysFont(None, 48)
        self.small_font = pygame.font.SysFont(None, 24)

    def close_display(self):
        try:
            pygame.mouse.set_visible(True)
            pygame.quit()
        except Exception:
            pass

    def _target_position(self, direction):
        cx, cy = self.centre
        d = config.TARGET_OFFSET_PX
        pos = {
            "left":  (cx - d, cy),
            "right": (cx + d, cy),
            "up":    (cx, cy - d),
            "down":  (cx, cy + d),
        }[direction]
        # Keep the target on screen whatever the panel size is.
        margin = config.TARGET_RADIUS_PX + 5
        return (int(min(max(pos[0], margin), self.width - margin)),
                int(min(max(pos[1], margin), self.height - margin)))

    def _blit_status(self, text):
        if not config.SHOW_TRIAL_NUMBER or not text:
            return
        surface = self.small_font.render(text, True, (60, 60, 60))
        self.screen.blit(surface, (10, 10))

    def _assessment_preview_rect(self):
        margin = max(0, int(config.ASSESSMENT_PREVIEW_MARGIN))
        width = min(int(config.ASSESSMENT_PREVIEW_WIDTH),
                    max(1, self.width - 2 * margin))
        height = min(int(config.ASSESSMENT_PREVIEW_HEIGHT),
                     max(1, self.height - 2 * margin))
        return pygame.Rect(self.width - width - margin, margin, width, height)

    def _draw_assessment_preview(self, force=False):
        """Draw the latest eye frame without touching the capture thread."""
        if not config.ASSESSMENT_PREVIEW:
            return None

        now = time.perf_counter()
        interval = 1.0 / max(1.0, float(config.ASSESSMENT_PREVIEW_FPS))
        if not force and now - self._preview_last_update < interval:
            return None
        self._preview_last_update = now

        panel = self._assessment_preview_rect()
        frame, sample = self.sampler.get_latest_preview()
        self.screen.fill((10, 10, 10), panel)
        if frame is None:
            waiting = self.small_font.render("Waiting for eye camera", True,
                                             (170, 170, 170))
            self.screen.blit(waiting, waiting.get_rect(center=panel.center))
        else:
            frame_h, frame_w = frame.shape[:2]
            scale = min(panel.width / frame_w, panel.height / frame_h)
            view_size = (max(1, int(frame_w * scale)),
                         max(1, int(frame_h * scale)))
            rgb = np.repeat(frame[:, :, np.newaxis], 3, axis=2)
            surface = pygame.surfarray.make_surface(np.swapaxes(rgb, 0, 1))
            if surface.get_size() != view_size:
                surface = pygame.transform.smoothscale(surface, view_size)
            view_rect = surface.get_rect(center=panel.center)
            self.screen.blit(surface, view_rect)

            found = (sample is not None and sample.found and
                     not math.isnan(sample.x) and not math.isnan(sample.y))
            if found:
                marker = (view_rect.left + int(sample.x * scale),
                          view_rect.top + int(sample.y * scale))
                radius = max(3, int(sample.radius * scale))
                pygame.draw.circle(self.screen, (40, 220, 80), marker,
                                   radius, 2)
                indicator = (40, 220, 80)
            else:
                indicator = (240, 130, 100)
            pygame.draw.circle(self.screen, indicator,
                               (panel.left + 8, panel.bottom - 8), 4)

        pygame.draw.rect(self.screen, (100, 100, 100), panel, 1)
        return panel

    def _draw_fixation(self, status=""):
        self.screen.fill(config.BACKGROUND_COLOR)
        pygame.draw.circle(self.screen, config.FIXATION_COLOR, self.centre,
                           config.FIXATION_RADIUS_PX)
        self._blit_status(status)
        self._draw_assessment_preview(force=True)
        pygame.display.flip()

    def _draw_target(self, direction, status=""):
        """
        Draw fixation + target and return the target onset timestamp,
        recorded immediately after the buffer flip.
        """
        self.screen.fill(config.BACKGROUND_COLOR)
        pygame.draw.circle(self.screen, config.FIXATION_COLOR, self.centre,
                           config.FIXATION_RADIUS_PX)
        pygame.draw.circle(self.screen, config.TARGET_COLOR,
                           self._target_position(direction),
                           config.TARGET_RADIUS_PX)
        self._blit_status(status)
        self._draw_assessment_preview(force=True)
        pygame.display.flip()
        onset = time.perf_counter()
        return onset + config.DISPLAY_LATENCY_COMPENSATION_MS / 1000.0

    def _message(self, lines, colour=(220, 220, 220)):
        self.screen.fill(config.BACKGROUND_COLOR)
        total = len(lines) * 55
        y = self.centre[1] - total // 2
        for line in lines:
            surface = self.font.render(line, True, colour)
            rect = surface.get_rect(center=(self.centre[0], y))
            self.screen.blit(surface, rect)
            y += 55
        pygame.display.flip()

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    def _poll_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise AbortTest("window closed")
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    raise AbortTest("user pressed ESC/Q")
                return event.key
        return None

    def _wait(self, duration, poll_interval=0.002, show_preview=False):
        """Sleep while staying responsive to the abort keys."""
        end = time.perf_counter() + duration
        while time.perf_counter() < end:
            self._poll_events()
            self._check_sampler()
            if show_preview:
                preview_rect = self._draw_assessment_preview()
                if preview_rect is not None:
                    pygame.display.update(preview_rect)
            time.sleep(poll_interval)

    def _wait_for_key(self, keys=(pygame.K_SPACE,)):
        while True:
            key = self._poll_events()
            if key in keys:
                return key
            time.sleep(0.01)

    def _check_sampler(self):
        if self.sampler.error is not None:
            raise AbortTest("camera failure: %s" % self.sampler.error)

    def run_camera_check(self):
        """Show an annotated live feed before calibration begins."""
        if not config.VIDEO_FEEDBACK:
            return

        clock = pygame.time.Clock()
        while True:
            key = self._poll_events()
            if key == pygame.K_SPACE:
                return
            self._check_sampler()

            frame, sample = self.sampler.get_latest_preview()
            self.screen.fill(config.BACKGROUND_COLOR)

            if frame is None:
                waiting = self.font.render("Waiting for camera...", True,
                                           (220, 220, 220))
                self.screen.blit(waiting, waiting.get_rect(center=self.centre))
            else:
                frame_h, frame_w = frame.shape[:2]
                scale = min(config.VIDEO_FEEDBACK_MAX_WIDTH / frame_w,
                            config.VIDEO_FEEDBACK_MAX_HEIGHT / frame_h,
                            1.0)
                view_w = max(1, int(frame_w * scale))
                view_h = max(1, int(frame_h * scale))

                # Pygame surfarray expects width x height x channels.
                rgb = np.repeat(frame[:, :, np.newaxis], 3, axis=2)
                surface = pygame.surfarray.make_surface(np.swapaxes(rgb, 0, 1))
                if (view_w, view_h) != (frame_w, frame_h):
                    surface = pygame.transform.smoothscale(surface,
                                                           (view_w, view_h))

                view_rect = surface.get_rect(center=(self.centre[0],
                                                     self.centre[1] - 25))
                self.screen.blit(surface, view_rect)
                pygame.draw.rect(self.screen, (100, 100, 100), view_rect, 1)

                position = (self.sampler.get_position_status()
                            if config.CAMERA_BACKEND == "webcam" else None)
                guidance = None
                positioned = False
                if config.CAMERA_BACKEND == "webcam":
                    guidance, positioned = webcam_position_guidance(position)
                if position and position.get("face_found"):
                    face_rect = pygame.Rect(
                        view_rect.left + int(position["left"] * view_w),
                        view_rect.top + int(position["top"] * view_h),
                        max(1, int((position["right"] - position["left"]) * view_w)),
                        max(1, int((position["bottom"] - position["top"]) * view_h)),
                    )
                    box_colour = ((80, 220, 120) if positioned
                                  else (240, 190, 80))
                    pygame.draw.rect(self.screen, box_colour, face_rect, 2)

                found = sample is not None and sample.found and \
                    not math.isnan(sample.x) and not math.isnan(sample.y)
                if found:
                    marker_x = view_rect.left + int(sample.x * scale)
                    marker_y = view_rect.top + int(sample.y * scale)
                    marker_r = max(4, int(sample.radius * scale))
                    pygame.draw.circle(self.screen, (40, 220, 80),
                                       (marker_x, marker_y), marker_r, 2)
                    pygame.draw.line(self.screen, (255, 80, 80),
                                     (marker_x - 8, marker_y),
                                     (marker_x + 8, marker_y), 1)
                    pygame.draw.line(self.screen, (255, 80, 80),
                                     (marker_x, marker_y - 8),
                                     (marker_x, marker_y + 8), 1)
                    status = "Pupil detected | confidence %.2f" % sample.confidence
                    status_colour = (80, 230, 120)
                else:
                    status = "Pupil not detected"
                    status_colour = (240, 130, 100)

                if config.CAMERA_BACKEND == "webcam":
                    status = guidance
                    status_colour = ((80, 230, 120) if positioned
                                     else (240, 190, 80))
                status_surface = self.small_font.render(status, True, status_colour)
                self.screen.blit(status_surface,
                                 status_surface.get_rect(center=(self.centre[0],
                                                                 self.height - 72)))

            help_surface = self.small_font.render(
                "Camera check - SPACE to calibrate | Q or ESC to exit", True,
                (210, 210, 210))
            self.screen.blit(help_surface,
                             help_surface.get_rect(center=(self.centre[0],
                                                           self.height - 38)))
            pygame.display.flip()
            clock.tick(max(1, int(config.VIDEO_FEEDBACK_FPS)))

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------
    def run_calibration(self):
        """
        Record the resting pupil position while the participant fixates the
        centre. Establishes baseline position, noise level and frame timing.
        """
        self._message(["Calibration", "Look at the centre dot",
                       "Press SPACE to begin"])
        self._wait_for_key()

        self._draw_fixation("calibrating")
        start = time.perf_counter()
        self._wait(config.CALIBRATION_DURATION_S, show_preview=True)
        end = time.perf_counter()

        samples = self.sampler.get_samples(start, end)
        found = [s for s in samples if s.found]
        n_total = max(1, len(samples))
        rate = len(found) / n_total

        if len(found) < 10:
            self._message(["Calibration failed", "Pupil not detected"],
                          (220, 120, 120))
            self._wait(3.0)
            raise AbortTest("calibration failed: pupil not detected")

        xs = np.array([s.x for s in found])
        ys = np.array([s.y for s in found])
        noise = float(math.hypot(np.std(xs), np.std(ys)))
        times = np.array([s.timestamp for s in found])
        dt = float(np.median(np.diff(times))) if times.size > 1 else float("nan")
        fps = (1.0 / dt) if dt and dt > 0 else float("nan")

        self.baseline = (float(np.median(xs)), float(np.median(ys)), noise)

        print("[calibration] detection rate %.0f%%, noise %.2f px, "
              "effective %.1f fps" % (rate * 100, noise, fps))

        problems = []
        if rate < config.CALIBRATION_MIN_DETECTION_RATE:
            problems.append("Low detection rate: %.0f%%" % (rate * 100))
        if noise > config.CALIBRATION_MAX_NOISE_PX:
            problems.append("High position noise: %.1f px" % noise)
        max_interval = (config.WEBCAM_MAX_MEDIAN_SAMPLE_INTERVAL_S
                        if config.CAMERA_BACKEND == "webcam"
                        else config.MAX_MEDIAN_SAMPLE_INTERVAL_S)
        if not math.isnan(dt) and dt > max_interval:
            problems.append("Slow sampling: %.1f fps" % fps)

        if problems:
            lines = ["Calibration warning"] + problems
            if config.CALIBRATION_ALLOW_CONTINUE:
                lines.append("SPACE = continue, Q = quit")
                self._message(lines, (230, 200, 120))
                self._wait_for_key()
            else:
                self._message(lines, (220, 120, 120))
                self._wait(4.0)
                raise AbortTest("calibration quality below threshold")

        return {"baseline_x": self.baseline[0], "baseline_y": self.baseline[1],
                "noise_px": noise, "detection_rate": rate, "fps": fps}

    # ------------------------------------------------------------------
    # Trials
    # ------------------------------------------------------------------
    def _trial_directions(self):
        """Randomised directions, balanced as far as NUM_TRIALS allows."""
        dirs = []
        while len(dirs) < config.NUM_TRIALS:
            block = list(config.TARGET_DIRECTIONS)
            self.rng.shuffle(block)
            dirs.extend(block)
        return dirs[:config.NUM_TRIALS]

    def run_trials(self):
        """Run every trial. A failed trial is recorded, never fatal."""
        self._message(["Prosaccade test", "Look at the centre dot,",
                       "then at the dot that appears", "SPACE to start"])
        self._wait_for_key()

        trials = []
        directions = self._trial_directions()

        for index, direction in enumerate(directions, start=1):
            status = "trial %d/%d" % (index, config.NUM_TRIALS)
            try:
                trials.append(self._run_single_trial(index, direction, status))
            except AbortTest:
                raise
            except Exception as exc:                 # never kill the session
                print("[trial %d] error: %s" % (index, exc))
                trials.append(TrialResult(
                    trial=index, direction=direction,
                    target_onset_timestamp=float("nan"),
                    saccade_onset_timestamp=float("nan"),
                    prosaccade_latency_ms=float("nan"),
                    confidence=0.0, valid=False, reason="trial_error:%s" % exc))

            self._draw_fixation(status)
            self._wait(config.INTER_TRIAL_INTERVAL_S, show_preview=True)

        return trials

    def _run_single_trial(self, index, direction, status):
        # 1-2. Fixation for a jittered duration.
        self._draw_fixation(status)
        fixation = config.FIXATION_DURATION_S
        if config.FIXATION_JITTER_S > 0:
            fixation += self.rng.uniform(0.0, config.FIXATION_JITTER_S)
        self._wait(fixation, show_preview=True)

        # 3-4. Target onset, timestamped at the flip.
        target_onset = self._draw_target(direction, status)

        # 5. Watch the eye.
        self._wait(config.POST_TARGET_WINDOW_S, show_preview=True)

        samples = self.sampler.get_samples(
            target_onset - config.BASELINE_DURATION_S - 0.05,
            target_onset + config.POST_TARGET_WINDOW_S)

        # 6-7. Saccade onset and latency.
        result = detect_saccade(samples, target_onset, direction)

        # 8. Store. No latency is written unless a saccade was detected.
        return TrialResult(
            trial=index,
            direction=direction,
            target_onset_timestamp=target_onset,
            saccade_onset_timestamp=result.saccade_onset_time,
            prosaccade_latency_ms=result.latency_ms,
            confidence=result.confidence,
            valid=result.valid,
            reason=result.reason,
            n_samples=result.n_samples,
            median_interval_ms=result.median_interval_ms,
            peak_velocity=result.peak_velocity,
            samples=samples,
        )

    # ------------------------------------------------------------------
    def show_summary(self, summary):
        lines = ["Prosaccade Test Complete",
                 "Valid trials: %d/%d" % (summary["valid_trials"],
                                          summary["total_trials"])]
        if summary["valid_trials"]:
            lines.append("Mean latency: %.0f ms" % summary["mean_latency_ms"])
        if not math.isnan(summary["sd_latency_ms"]):
            lines.append("SD: %.0f ms" % summary["sd_latency_ms"])
        lines.append("Press Q to exit")
        self._message(lines)
        try:
            self._wait_for_key(keys=(pygame.K_SPACE, pygame.K_RETURN))
        except AbortTest:
            pass
