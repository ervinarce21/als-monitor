#!/usr/bin/env python3
"""
NEXA speech-analysis module - command-line entry point.

The interactive menu exposes the currently functional microphone discovery
and database setup actions. Planned analysis commands remain available through
argparse and clearly report that they are not implemented yet.
"""

import argparse
import shutil
import sqlite3
import subprocess
import sys

from . import config


def _list_microphones_with_arecord(reason):
    """Fall back to ALSA device discovery when sounddevice is unavailable."""
    arecord = shutil.which("arecord")
    if arecord is None:
        print("ERROR: sounddevice is not available (%s)." % reason)
        print("Install audio support with:")
        print("  sudo apt install python3-sounddevice libportaudio2 alsa-utils")
        return 1

    print("Python sounddevice is unavailable (%s)." % reason)
    print("Showing ALSA capture devices instead:\n")
    result = subprocess.run(
        [arecord, "-l"], capture_output=True, text=True, check=False)
    output = (result.stdout or "") + (result.stderr or "")
    print(output.strip() or "No ALSA capture devices were reported.")
    return 0 if result.returncode == 0 else 1


def cmd_list_microphones(_args):
    """List input-capable audio devices, e.g. to find MIC_DEVICE_INDEX."""
    try:
        import sounddevice as sd
    except Exception as exc:
        return _list_microphones_with_arecord(exc)

    try:
        devices = sd.query_devices()
    except Exception as exc:
        return _list_microphones_with_arecord(exc)

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


def _prompt_command_arguments(command):
    """Collect arguments needed to dispatch one CLI command."""
    if command == "record":
        print("1) Sustained vowel")
        print("2) Connected speech")
        task_choice = input("Select task [1-2, blank for default]: ").strip()
        task = {
            "1": config.TASK_SUSTAINED_VOWEL,
            "2": config.TASK_CONNECTED_SPEECH,
        }.get(task_choice)
        if task_choice and task is None:
            print("Invalid task selection.")
            return None

        duration = input("Duration in seconds [default]: ").strip()
        output = input("Output WAV path [automatic]: ").strip()
        arguments = [command]
        if task:
            arguments.extend(["--task", task])
        if duration:
            arguments.extend(["--duration", duration])
        if output:
            arguments.extend(["--out", output])
        return arguments

    if command in {
            "analyze", "analyze-speech", "analyze-sustained-vowel",
            "analyze-reading"}:
        wav_path = input("WAV file path: ").strip()
        if not wav_path:
            print("A WAV file path is required.")
            return None
        return [command, wav_path]

    if command == "compare-baseline":
        participant_id = input("Participant ID: ").strip()
        session_id = input("Session ID: ").strip()
        if not participant_id or not session_id:
            print("Participant ID and session ID are required.")
            return None
        return [command, participant_id, session_id]

    return [command]


def run_interactive_menu(parser):
    """Run speech commands until the user chooses to exit."""
    commands = {
        "1": ("List microphones", "list-microphones"),
        "2": ("Initialize database", "init-db"),
        "3": ("Record WAV", "record"),
        "4": ("Validate/analyze WAV", "analyze"),
        "5": ("Analyze connected speech", "analyze-speech"),
        "6": ("Analyze sustained vowel", "analyze-sustained-vowel"),
        "7": ("Analyze reading", "analyze-reading"),
        "8": ("Show stored results", "show-results"),
        "9": ("Compare session with baseline", "compare-baseline"),
    }

    while True:
        print("\nNEXA Speech Analysis")
        print("1) List microphones")
        print("2) Initialize database")
        print("3) Record WAV")
        print("4) Validate/analyze WAV")
        print("5) Analyze connected speech")
        print("6) Analyze sustained vowel")
        print("7) Analyze reading")
        print("8) Show stored results")
        print("9) Compare session with baseline")
        print("10) Show command help")
        print("11) Exit")

        try:
            choice = input("Select an action [1-11]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting speech analysis.")
            return 0

        if choice == "11":
            print("Exiting speech analysis.")
            return 0
        if choice == "10":
            print()
            parser.print_help()
            continue
        if choice not in commands:
            print("Invalid selection. Choose a number from 1 to 11.")
            continue

        label, command = commands[choice]
        try:
            command_arguments = _prompt_command_arguments(command)
        except (EOFError, KeyboardInterrupt):
            print("\nAction cancelled.")
            continue
        if command_arguments is None:
            continue

        print("\n--- %s ---" % label)
        try:
            args = parser.parse_args(command_arguments)
        except SystemExit:
            print("Action cancelled because an argument was invalid.")
            continue
        result = args.func(args)
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
