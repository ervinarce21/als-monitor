#!/usr/bin/env python3
"""
NEXA - oculomotor module entry point.

Chain: OV9281 -> frame capture -> pupil detection -> timestamped samples
-> velocity -> saccade onset -> prosaccade latency -> CSV -> summary.

Measurement tool only. It reports prosaccade latency in milliseconds and
descriptive statistics; it does not classify, score or diagnose anything.
"""

import sys
import traceback

import config
import results as results_mod
from camera import CameraError
from prosaccade_test import AbortTest, ProsaccadeTest
from sampler import EyeSampler


def main():
    sampler = EyeSampler(buffer_seconds=10.0, expected_fps=config.CAMERA_FPS)
    test = None
    trials = []
    exit_code = 0

    # ---- camera -------------------------------------------------------
    try:
        sampler.start()
    except CameraError as exc:
        print("[fatal] %s" % exc)
        return 2
    except Exception as exc:
        print("[fatal] unexpected camera error: %s" % exc)
        return 2

    # ---- test ---------------------------------------------------------
    try:
        test = ProsaccadeTest(sampler)
        test.init_display()
        test.run_camera_check()
        test.run_calibration()
        trials = test.run_trials()
    except AbortTest as exc:
        print("[abort] %s" % exc)
        exit_code = 1
    except Exception:
        traceback.print_exc()
        exit_code = 3
    finally:
        # ---- output: always save whatever was collected ---------------
        if trials:
            summary = results_mod.summarise(trials)
            csv_path = results_mod.save_results_csv(trials)
            results_mod.save_raw_samples_csv(trials)
            results_mod.save_summary_csv(summary)
            results_mod.print_summary(summary)
            if csv_path:
                print("Results written to: %s" % csv_path)
            if test is not None and exit_code == 0:
                try:
                    test.show_summary(summary)
                except Exception:
                    pass
        else:
            print("No trials were completed.")

        print("Frames captured: %d (pupil missed in %d)"
              % (sampler.frames_captured, sampler.frames_dropped))

        if test is not None:
            test.close_display()
        sampler.stop()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
