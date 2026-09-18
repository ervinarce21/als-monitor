#!/usr/bin/env python3
"""
NEXA speech-analysis module - command-line entry point.

Provides interactive and direct commands for microphone discovery, recording,
acoustic analysis, result storage, and longitudinal baseline comparison.
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import wave
from datetime import datetime
from pathlib import Path

from . import config
from .analysis import analyze_wav


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


def cmd_record(args):
    """Record mono PCM16 audio from the configured microphone."""
    try:
        import sounddevice as sd
    except Exception as exc:
        print("ERROR: recording requires sounddevice: %s" % exc)
        print("Install with: sudo apt install python3-sounddevice libportaudio2")
        return 1
    task = args.task or config.TASK_CONNECTED_SPEECH
    default_duration = (config.SUSTAINED_VOWEL_TARGET_SECONDS
                        if task == config.TASK_SUSTAINED_VOWEL else 10.0)
    duration = args.duration or default_duration
    if duration <= 0 or duration > config.MAX_RECORDING_SECONDS:
        print("ERROR: duration must be between 0 and %d seconds."
              % config.MAX_RECORDING_SECONDS)
        return 1
    output = Path(args.out) if args.out else (
        config.RECORDINGS_DIR /
        ("%s_%s.wav" % (task, datetime.now().strftime("%Y%m%d_%H%M%S"))))
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        print("Recording %.1f seconds..." % duration)
        frames = int(duration * config.SAMPLE_RATE)
        audio = sd.rec(frames, samplerate=config.SAMPLE_RATE,
                       channels=config.CHANNELS, dtype="int16",
                       device=config.MIC_DEVICE_INDEX)
        sd.wait()
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(config.CHANNELS)
            wav.setsampwidth(config.SAMPLE_WIDTH_BITS // 8)
            wav.setframerate(config.SAMPLE_RATE)
            wav.writeframes(audio.astype("<i2").tobytes())
    except Exception as exc:
        print("ERROR: recording failed: %s" % exc)
        return 1
    print("Recording saved: %s" % output)
    return 0


def cmd_assess(args):
    """Record and immediately analyze one UI assessment."""
    output_dir = Path(os.environ.get("NEXA_OUTPUT_DIR", config.RESULTS_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / "speech_recording.wav"
    record_args = argparse.Namespace(
        task=args.task, duration=args.duration, out=str(wav_path))
    result = cmd_record(record_args)
    if result:
        return result
    try:
        metrics = analyze_wav(str(wav_path), args.task)
    except (OSError, ValueError, wave.Error) as exc:
        print("ERROR: could not analyze recording: %s" % exc)
        return 1
    if args.task == config.TASK_READING:
        try:
            with open(config.DEFAULT_PASSAGE_METADATA_PATH, "r") as handle:
                passage_metadata = json.load(handle)
            passage_text = config.DEFAULT_PASSAGE_PATH.read_text().strip()
            metrics["passage_name"] = passage_metadata.get("name")
            metrics["passage_word_count"] = len(passage_text.split())
            metrics["passage_expected_syllables"] = passage_metadata.get(
                "expected_syllables")
        except (OSError, json.JSONDecodeError):
            print("WARNING: Rainbow Passage metadata could not be loaded.")
    participant = os.environ.get("NEXA_PARTICIPANT_ID", args.participant)
    session_id = _store_analysis(
        str(wav_path), args.task, metrics, participant,
        args.session_id, args.baseline)
    if session_id is None:
        return 1
    summary_path = output_dir / "speech_summary.json"
    with open(summary_path, "w") as handle:
        json.dump(metrics, handle, indent=2)
    print("Analysis stored as session: %s" % session_id)
    print("Summary written to: %s" % summary_path)
    return 0


def _stage_existing_analysis(wav_path, metrics):
    """Write artifacts expected by NEXA UI when analyzing an existing WAV."""
    output_dir_value = os.environ.get("NEXA_OUTPUT_DIR")
    if not output_dir_value:
        return True

    output_dir = Path(output_dir_value)
    output_dir.mkdir(parents=True, exist_ok=True)
    source = Path(wav_path)
    staged_wav = output_dir / "speech_recording.wav"
    summary_path = output_dir / "speech_summary.json"
    try:
        if source.resolve() != staged_wav.resolve():
            shutil.copy2(str(source), str(staged_wav))
        with open(summary_path, "w") as handle:
            json.dump(metrics, handle, indent=2)
    except OSError as exc:
        print("ERROR: could not stage NEXA analysis output: %s" % exc)
        return False

    print("Recording copied to: %s" % staged_wav)
    print("Summary written to: %s" % summary_path)
    return True


def _store_analysis(wav_path, task, metrics, participant_id, session_id,
                    is_baseline):
    if cmd_init_db(None):
        return None
    participant_id = participant_id or config.PARTICIPANT_ID_DEFAULT
    session_id = session_id or "%s_%s" % (
        participant_id, datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    with sqlite3.connect(config.DATABASE_PATH) as conn:
        conn.execute("INSERT OR IGNORE INTO participant (participant_id) VALUES (?)",
                     (participant_id,))
        conn.execute(
            "INSERT INTO session (session_id, participant_id, is_baseline) "
            "VALUES (?, ?, ?)",
            (session_id, participant_id, 1 if is_baseline else 0))
        conn.execute(
            """INSERT INTO speech_assessment (
                session_id, task_name, audio_filename, sample_rate_hz,
                recording_duration_sec, speech_duration_sec,
                pause_duration_sec, num_pauses, pause_percentage, mean_f0_hz,
                hnr_db, quality_status, quality_flags, analysis_parameters,
                software_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, task, str(wav_path), metrics["sample_rate_hz"],
             metrics["recording_duration_sec"], metrics["speech_duration_sec"],
             metrics["pause_duration_sec"], metrics["num_pauses"],
             metrics["pause_percentage"], metrics["mean_f0_hz"],
             metrics["hnr_db"], metrics["quality_status"],
             json.dumps(metrics["quality_flags"]), json.dumps({
                 "pitch_floor_hz": config.F0_PITCH_FLOOR_HZ,
                 "pitch_ceiling_hz": config.F0_PITCH_CEILING_HZ,
                 "pause_threshold_sec": config.PAUSE_THRESHOLD_SECONDS,
             }), config.NEXA_SPEECH_MODULE_VERSION))
    return session_id


def _analysis_handler(task):
    def handler(args):
        try:
            metrics = analyze_wav(args.wav_path, task)
        except (OSError, ValueError, wave.Error) as exc:
            print("ERROR: could not analyze WAV: %s" % exc)
            return 1
        print("\nSpeech analysis")
        for key, value in metrics.items():
            if key != "task":
                print("  %-26s %s" % (key + ":", value))
        session_id = _store_analysis(
            args.wav_path, task, metrics, args.participant, args.session_id,
            args.baseline)
        if session_id is None:
            return 1
        if not _stage_existing_analysis(args.wav_path, metrics):
            return 1
        print("Stored as session: %s" % session_id)
        return 0
    return handler


def cmd_show_results(_args):
    if cmd_init_db(None):
        return 1
    with sqlite3.connect(config.DATABASE_PATH) as conn:
        rows = conn.execute(
            """SELECT s.session_id, s.participant_id, a.task_name,
                      a.recording_duration_sec, a.mean_f0_hz, a.hnr_db,
                      a.pause_percentage, a.quality_status
               FROM speech_assessment a JOIN session s USING (session_id)
               ORDER BY a.processed_at DESC LIMIT 50""").fetchall()
    if not rows:
        print("No speech results have been stored.")
        return 0
    for row in rows:
        print(" | ".join("" if value is None else str(value) for value in row))
    return 0


def cmd_compare_baseline(args):
    if cmd_init_db(None):
        return 1
    metrics = ("recording_duration_sec", "speech_duration_sec",
               "pause_percentage", "mean_f0_hz", "hnr_db")
    with sqlite3.connect(config.DATABASE_PATH) as conn:
        baseline = conn.execute(
            """SELECT a.recording_duration_sec, a.speech_duration_sec,
                      a.pause_percentage, a.mean_f0_hz, a.hnr_db
               FROM speech_assessment a JOIN session s USING (session_id)
               WHERE s.participant_id=? AND s.is_baseline=1
               ORDER BY s.session_datetime DESC LIMIT 1""",
            (args.participant_id,)).fetchone()
        current = conn.execute(
            """SELECT recording_duration_sec, speech_duration_sec,
                      pause_percentage, mean_f0_hz, hnr_db
               FROM speech_assessment WHERE session_id=? LIMIT 1""",
            (args.session_id,)).fetchone()
    if baseline is None or current is None:
        print("ERROR: baseline or requested session was not found.")
        return 1
    for name, base, value in zip(metrics, baseline, current):
        change = None if base in (None, 0) or value is None else 100 * (value-base)/base
        print("%-25s baseline=%s current=%s change=%s" %
              (name, base, value, "n/a" if change is None else "%.1f%%" % change))
    return 0


def _add_analysis_options(parser):
    parser.add_argument("wav_path")
    parser.add_argument("--participant", default=config.PARTICIPANT_ID_DEFAULT)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--baseline", action="store_true",
                        help="Mark this session as the participant baseline.")


def _prompt_command_arguments(command):
    """Collect arguments needed to dispatch one CLI command."""
    if command == "record":
        print("1) Sustained vowel")
        print("2) Connected speech")
        print("3) Reading")
        task_choice = input("Select task [1-3, blank for default]: ").strip()
        task = {
            "1": config.TASK_SUSTAINED_VOWEL,
            "2": config.TASK_CONNECTED_SPEECH,
            "3": config.TASK_READING,
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
        prog="nexa speech",
        description="NEXA speech-analysis module (research prototype, "
                     "not a diagnostic device).")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list-microphones",
                   help="List input audio devices and their index.") \
        .set_defaults(func=cmd_list_microphones)

    sub.add_parser("init-db",
                   help="Create/upgrade the SQLite database from schema.sql.") \
        .set_defaults(func=cmd_init_db)

    p = sub.add_parser("record", help="Record a mono PCM16 WAV file.")
    p.add_argument("--task", choices=[config.TASK_SUSTAINED_VOWEL,
                                      config.TASK_CONNECTED_SPEECH,
                                      config.TASK_READING],
                  required=False)
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--out", type=str, default=None)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser(
        "assess", help="Record and analyze one speech assessment.")
    p.add_argument("--task", choices=[config.TASK_SUSTAINED_VOWEL,
                                      config.TASK_CONNECTED_SPEECH,
                                      config.TASK_READING],
                   default=config.TASK_CONNECTED_SPEECH)
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--participant", default=config.PARTICIPANT_ID_DEFAULT)
    p.add_argument("--session-id", default=None)
    p.add_argument("--baseline", action="store_true")
    p.set_defaults(func=cmd_assess)

    p = sub.add_parser("analyze", help="Validate and analyze a WAV file.")
    _add_analysis_options(p)
    p.set_defaults(func=_analysis_handler(config.TASK_CONNECTED_SPEECH))

    p = sub.add_parser("analyze-speech",
                       help="Analyze connected speech.")
    _add_analysis_options(p)
    p.set_defaults(func=_analysis_handler(config.TASK_CONNECTED_SPEECH))

    p = sub.add_parser("analyze-sustained-vowel",
                       help="Analyze a sustained vowel, including F0 and HNR.")
    _add_analysis_options(p)
    p.set_defaults(func=_analysis_handler(config.TASK_SUSTAINED_VOWEL))

    p = sub.add_parser("analyze-reading",
                       help="Analyze timing in a read passage.")
    _add_analysis_options(p)
    p.set_defaults(func=_analysis_handler(config.TASK_READING))

    sub.add_parser("show-results", help="Print stored results.") \
        .set_defaults(func=cmd_show_results)

    p = sub.add_parser("compare-baseline",
                       help="Compare a session against participant baseline.")
    p.add_argument("participant_id")
    p.add_argument("session_id")
    p.set_defaults(func=cmd_compare_baseline)

    return parser


def main(argv=None):
    parser = build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args == ["menu"]:
        return run_interactive_menu(parser)

    args = parser.parse_args(raw_args)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
