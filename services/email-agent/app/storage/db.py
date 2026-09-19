"""SQLite schema + connection helper.

Two threads (the mail-polling pipeline and the job worker) write to this database
concurrently, so every write uses a short-lived connection in WAL mode with a busy
timeout, rather than one long-lived shared connection.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    sender_email TEXT NOT NULL,
    backend_user_id INTEGER NOT NULL,
    source_message_id TEXT NOT NULL,
    operation TEXT NOT NULL DEFAULT 'submit_transcript',
    status TEXT NOT NULL,
    group_hint TEXT,
    resolved_group_id INTEGER,
    resolved_group_name TEXT,
    attachment_filename TEXT,
    attachment_storage_path TEXT,
    meeting_date TEXT,
    meeting_date_source TEXT,
    speakers_json TEXT,
    backend_meeting_id INTEGER,
    backend_raw_file_id INTEGER,
    resolved_attendees_json TEXT,
    unresolved_speakers_json TEXT,
    transcript_focus TEXT,
    github_focus TEXT,
    trello_focus TEXT,
    comment_text TEXT,
    error TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    last_response_message_id TEXT,
    in_reply_to_message_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_sender ON jobs (sender_email);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL,
    sender_email TEXT NOT NULL,
    auth_result TEXT NOT NULL,
    operation TEXT,
    job_id TEXT,
    outcome TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    to_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body_text TEXT NOT NULL,
    attachments_json TEXT,
    in_reply_to_message_id TEXT,
    references_header TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox (status);

CREATE TABLE IF NOT EXISTS message_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outbox_id INTEGER NOT NULL UNIQUE,
    job_id TEXT,
    message_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_message_links_job ON message_links (job_id);

CREATE TABLE IF NOT EXISTS pending_clarifications (
    job_id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    expected_field TEXT NOT NULL,
    options_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_reports (
    report_id TEXT PRIMARY KEY,
    group_id INTEGER NOT NULL,
    group_name TEXT NOT NULL,
    owner_email TEXT NOT NULL,
    backend_user_id INTEGER NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    status TEXT NOT NULL,
    report_text TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_reports_period_group
    ON weekly_reports (group_id, period_start, period_end);

CREATE TABLE IF NOT EXISTS report_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT NOT NULL,
    source TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    title TEXT NOT NULL,
    event_date TEXT,
    content TEXT NOT NULL,
    citation TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(report_id, source, evidence_id)
);

CREATE INDEX IF NOT EXISTS idx_report_evidence_report ON report_evidence (report_id);

CREATE TABLE IF NOT EXISTS admin_alerts (
    category TEXT PRIMARY KEY,
    last_sent_at TEXT NOT NULL
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a new short-lived connection with WAL mode and a busy timeout."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        if "comment_text" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN comment_text TEXT")
    finally:
        conn.close()
