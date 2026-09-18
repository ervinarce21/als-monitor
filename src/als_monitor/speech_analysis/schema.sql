-- NEXA speech module longitudinal database schema.

PRAGMA foreign_keys = ON;

-- One row per research participant. Store an ID, not a name.
CREATE TABLE IF NOT EXISTS participant (
    participant_id      TEXT PRIMARY KEY,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    notes                 TEXT
);

-- One row per recording session (a participant has many sessions over time).
CREATE TABLE IF NOT EXISTS session (
    session_id            TEXT PRIMARY KEY,
    participant_id        TEXT NOT NULL REFERENCES participant(participant_id),
    session_datetime       TEXT NOT NULL DEFAULT (datetime('now')),
    is_baseline            INTEGER NOT NULL DEFAULT 0,   -- 1 = baseline session
    notes                   TEXT
);

-- One row per analyzed audio task (sustained vowel or connected speech)
-- within a session. Kept separate from statistics/comparisons (later steps).
CREATE TABLE IF NOT EXISTS speech_assessment (
    assessment_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id               TEXT NOT NULL REFERENCES session(session_id),
    task_name                 TEXT NOT NULL,     -- sustained_vowel | connected_speech | reading
    audio_filename             TEXT NOT NULL,
    sample_rate_hz             INTEGER,
    recording_duration_sec     REAL,

    speech_duration_sec         REAL,
    pause_duration_sec           REAL,
    num_pauses                    INTEGER,

    speaking_rate_wpm              REAL,
    articulation_rate_syll_per_sec  REAL,
    pause_percentage                 REAL,
    mean_f0_hz                        REAL,
    hnr_db                              REAL,

    quality_status                     TEXT,     -- VALID | WARNING | REJECTED
    quality_flags                        TEXT,   -- JSON-encoded list of flag strings

    analysis_parameters                   TEXT,  -- JSON: all thresholds/settings used
    software_version                       TEXT,
    processed_at                            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_session_participant
    ON session(participant_id);

CREATE INDEX IF NOT EXISTS idx_assessment_session
    ON speech_assessment(session_id);
