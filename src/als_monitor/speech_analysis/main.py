#!/usr/bin/env python3
"""
NEXA speech-analysis module - command-line entry point.

The interactive menu exposes the currently functional microphone discovery
and database setup actions. Planned analysis commands remain available through
argparse and clearly report that they are not implemented yet.
"""

import argparse
import sqlite3
import sys

from . import config


def cmd_list_microphones(_args):
    """List input-capable audio devices, e.g. to find MIC_DEVICE_INDEX."""
    try:
        import sounddevice as sd
    except Exception as exc:
        print("ERROR: sounddevice is not available (%s). "
              "Install it with: pip install sounddevice "
              "(and `sudo apt install libportaudio2` on Raspberry Pi OS)."
              % exc)
        return 1

    try:
        devices = sd.query_devices()
    except Exception as exc:
        print("ERROR: could not query audio devices: %s" % exc)
        return 1

    inputs = [(i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    if not inputs:
        print("No input-capable audio devices were found. "
              "Check that the USB microphone is plugged in.")
        return 1

    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = None

    print("Input-capable audio devices:")
    for index, dev in inputs:
        marker = " (default)" if index == default_in else ""
        print("  [%d] %s | channels=%d | default sample rate=%.0f Hz%s"
              % (index, dev["name"], dev["max_input_channels"],
                 dev["default_samplerate"], marker))
    print("\nIf the wrong device is used for recording, set "
          "MIC_DEVICE_INDEX in config.py to the index shown above.")
    return 0


def cmd_init_db(_args):
    """Create the SQLite database file from schema.sql if it does not exist."""
    try:
        with open(config.SCHEMA_PATH, "r") as handle:
            schema_sql = handle.read()
    except OSError as exc:
        print("ERROR: could not read schema file (%s): %s"
              % (config.SCHEMA_PATH, exc))
        return 1

    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        with conn:
            conn.executescript(schema_sql)
        conn.close()
    except sqlite3.Error as exc:
        print("ERROR: could not initialise the database: %s" % exc)
        return 1

    print("Database ready at: %s" % config.DATABASE_PATH)
    return 0


def _not_yet_implemented(command_name, step):
    def handler(_args):
        print("'%s' is not implemented yet (planned for STEP %d)."
              % (command_name, step))
        return 1
    return handler


def run_interactive_menu(parser):
    """Run functional speech actions until the user chooses to exit."""
    actions = {
        "1": ("List microphones", cmd_list_microphones),
        "2": ("Initialize database", cmd_init_db),
    }

    while True:
        print("\nNEXA Speech Analysis")
        print("1) List microphones")
        print("2) Initialize database")
        print("3) Show all commands")
        print("4) Exit")

        try:
            choice = input("Select an action [1-4]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting speech analysis.")
            return 0

        if choice == "4":
            print("Exiting speech analysis.")
            return 0
        if choice == "3":
            print()
            parser.print_help()
            continue
        if choice not in actions:
            print("Invalid selection. Choose 1, 2, 3, or 4.")
            continue

        label, action = actions[choice]
        print("\n--- %s ---" % label)
        result = action(None)
        if result == 0:
            print("Action completed successfully.")
        else:
            print("Action failed. Review the message above.")

        try:
            input("\nPress Enter to return to the speech menu...")
        except (EOFError, KeyboardInterrupt):
            print()
            return result


def build_parser():
    parser = argparse.ArgumentParser(
        prog="als-monitor speech",
        description="NEXA speech-analysis module (research prototype, "
                     "not a diagnostic device).")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list-microphones",
                   help="List input audio devices and their index.") \
        .set_defaults(func=cmd_list_microphones)

    sub.add_parser("init-db",
                   help="Create/upgrade the SQLite database from schema.sql.") \
        .set_defaults(func=cmd_init_db)

    p = sub.add_parser("record", help="Record a WAV file (STEP 2).")
    p.add_argument("--task", choices=[config.TASK_SUSTAINED_VOWEL,
                                      config.TASK_CONNECTED_SPEECH],
                  required=False)
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--out", type=str, default=None)
    p.set_defaults(func=_not_yet_implemented("record", 2))

    p = sub.add_parser("analyze", help="Validate/analyze a WAV file (STEP 3).")
    p.add_argument("wav_path")
    p.set_defaults(func=_not_yet_implemented("analyze", 3))

    p = sub.add_parser("analyze-speech",
                       help="Full 5-feature analysis of connected speech "
                            "(STEP 12).")
    p.add_argument("wav_path")
    p.set_defaults(func=_not_yet_implemented("analyze-speech", 12))

    p = sub.add_parser("analyze-sustained-vowel",
                       help="F0 + HNR analysis of a sustained /a/ (STEP 7).")
    p.add_argument("wav_path")
    p.set_defaults(func=_not_yet_implemented("analyze-sustained-vowel", 7))

    p = sub.add_parser("analyze-reading",
                       help="Timing analysis of a read passage (STEP 11).")
    p.add_argument("wav_path")
    p.set_defaults(func=_not_yet_implemented("analyze-reading", 11))

    sub.add_parser("show-results", help="Print stored results (STEP 13).") \
        .set_defaults(func=_not_yet_implemented("show-results", 13))

    p = sub.add_parser("compare-baseline",
                       help="Compare a session against baseline (STEP 14).")
    p.add_argument("participant_id")
    p.add_argument("session_id")
    p.set_defaults(func=_not_yet_implemented("compare-baseline", 14))

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        if sys.stdin.isatty():
            return run_interactive_menu(parser)
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
