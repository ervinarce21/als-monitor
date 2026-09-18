"""
NEXA UI - Data store

SQLite for structured participant/session/trial metadata. Raw modality output
(CSV/JSON produced by the existing modality scripts) is copied into a
per-session folder and referenced by path, never re-parsed into the database.
"""

import json
import os
import sqlite3
from datetime import datetime

import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT,
    birth_year INTEGER,
    handedness TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER NOT NULL,
    operator TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    notes TEXT,
    FOREIGN KEY (participant_id) REFERENCES participants(id)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    modality TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,          -- completed | aborted | failed
    exit_code INTEGER,
    metrics_json TEXT,             -- parsed summary metrics
    raw_path TEXT,                 -- folder holding this run's raw output files
    operator_notes TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS assessment_baselines (
    participant_id INTEGER NOT NULL,
    modality TEXT NOT NULL,
    task TEXT NOT NULL DEFAULT '',
    run_id INTEGER NOT NULL,
    set_at TEXT NOT NULL,
    PRIMARY KEY (participant_id, modality, task),
    FOREIGN KEY (participant_id) REFERENCES participants(id),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_participant ON sessions(participant_id);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);
"""


def _now():
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path=None):
        config.ensure_dirs()
        self.path = path or config.DB_PATH
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    # -- participants -------------------------------------------------------

    def create_participant(self, code, display_name="", birth_year=None,
                           handedness="", notes=""):
        cur = self.conn.execute(
            "INSERT INTO participants (code, display_name, birth_year, handedness, notes, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (code.strip(), display_name.strip(), birth_year, handedness, notes, _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_participant(self, pid, **fields):
        allowed = {"display_name", "birth_year", "handedness", "notes"}
        sets, vals = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                vals.append(v)
        if not sets:
            return
        vals.append(pid)
        self.conn.execute(f"UPDATE participants SET {', '.join(sets)} WHERE id = ?", vals)
        self.conn.commit()

    def list_participants(self, search=""):
        if search:
            like = f"%{search}%"
            rows = self.conn.execute(
                "SELECT * FROM participants WHERE code LIKE ? OR display_name LIKE ?"
                " ORDER BY created_at DESC", (like, like)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM participants ORDER BY created_at DESC"
            ).fetchall()
        return rows

    def get_participant(self, pid):
        return self.conn.execute(
            "SELECT * FROM participants WHERE id = ?", (pid,)
        ).fetchone()

    def participant_code_exists(self, code):
        row = self.conn.execute(
            "SELECT 1 FROM participants WHERE code = ?", (code.strip(),)
        ).fetchone()
        return row is not None

    # -- sessions -------------------------------------------------------

    def start_session(self, participant_id, operator="", notes=""):
        cur = self.conn.execute(
            "INSERT INTO sessions (participant_id, operator, started_at, notes)"
            " VALUES (?, ?, ?, ?)",
            (participant_id, operator, _now(), notes),
        )
        self.conn.commit()
        return cur.lastrowid

    def end_session(self, session_id, notes=None):
        if notes is None:
            self.conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?", (_now(), session_id)
            )
        else:
            self.conn.execute(
                "UPDATE sessions SET ended_at = ?, notes = ? WHERE id = ?",
                (_now(), notes, session_id),
            )
        self.conn.commit()

    def get_session(self, session_id):
        return self.conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()

    def list_sessions(self, participant_id=None, limit=200):
        if participant_id is not None:
            return self.conn.execute(
                "SELECT s.*, p.code AS participant_code, p.display_name"
                " FROM sessions s JOIN participants p ON p.id = s.participant_id"
                " WHERE s.participant_id = ? ORDER BY s.started_at DESC LIMIT ?",
                (participant_id, limit),
            ).fetchall()
        return self.conn.execute(
            "SELECT s.*, p.code AS participant_code, p.display_name"
            " FROM sessions s JOIN participants p ON p.id = s.participant_id"
            " ORDER BY s.started_at DESC LIMIT ?", (limit,)
        ).fetchall()

    # -- runs -------------------------------------------------------

    def record_run(self, session_id, modality, started_at, status,
                   exit_code=None, metrics=None, raw_path="", operator_notes=""):
        cur = self.conn.execute(
            "INSERT INTO runs (session_id, modality, started_at, ended_at, status,"
            " exit_code, metrics_json, raw_path, operator_notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, modality, started_at, _now(), status, exit_code,
             json.dumps(metrics or {}), raw_path, operator_notes),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_runs(self, session_id):
        return self.conn.execute(
            "SELECT * FROM runs WHERE session_id = ? ORDER BY started_at ASC",
            (session_id,),
        ).fetchall()

    def latest_run_for_modality(self, session_id, modality):
        return self.conn.execute(
            "SELECT * FROM runs WHERE session_id = ? AND modality = ?"
            " ORDER BY started_at DESC LIMIT 1", (session_id, modality)
        ).fetchone()

    def set_baseline_run(self, participant_id, modality, task, run_id):
        run = self.conn.execute(
            "SELECT r.id FROM runs r JOIN sessions s ON s.id = r.session_id"
            " WHERE r.id = ? AND r.modality = ? AND s.participant_id = ?",
            (run_id, modality, participant_id),
        ).fetchone()
        if run is None:
            raise ValueError("The selected assessment does not belong to this participant.")
        self.conn.execute(
            "INSERT INTO assessment_baselines"
            " (participant_id, modality, task, run_id, set_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(participant_id, modality, task) DO UPDATE SET"
            " run_id = excluded.run_id, set_at = excluded.set_at",
            (participant_id, modality, task or "", run_id, _now()),
        )
        self.conn.commit()

    def get_baseline_run(self, participant_id, modality, task=""):
        return self.conn.execute(
            "SELECT r.* FROM assessment_baselines b"
            " JOIN runs r ON r.id = b.run_id"
            " WHERE b.participant_id = ? AND b.modality = ? AND b.task = ?",
            (participant_id, modality, task or ""),
        ).fetchone()

    @staticmethod
    def run_metrics(run_row):
        try:
            return json.loads(run_row["metrics_json"] or "{}")
        except (json.JSONDecodeError, TypeError, KeyError):
            return {}

    def session_raw_dir(self, session_id):
        d = os.path.join(config.RAW_DATA_DIR, f"session_{session_id:05d}")
        os.makedirs(d, exist_ok=True)
        return d
