import sqlite3
from pathlib import Path

import pytest

from app.jobs.models import JobState
from app.jobs.store import (
    InvalidTransition,
    JobStore,
    Outbox,
    ProcessedMessageStore,
)
from app.storage.db import SCHEMA, init_db


def test_create_job_allocates_sequential_ids(db_path: Path):
    store = JobStore(db_path)
    j1 = store.create_job("alice@uni.ac.uk", 12, "<msg-1@mail>")
    j2 = store.create_job("alice@uni.ac.uk", 12, "<msg-2@mail>")
    assert j1.job_id != j2.job_id
    assert j1.job_id.startswith("DIAR-")
    assert j1.status == JobState.RECEIVED


def test_get_returns_none_for_missing_job(db_path: Path):
    store = JobStore(db_path)
    assert store.get("DIAR-2026-0101-9999") is None


def test_get_owned_hides_jobs_from_non_owner(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<msg-1@mail>")
    assert store.get_owned(job.job_id, "alice@uni.ac.uk") is not None
    assert store.get_owned(job.job_id, "mallory@evil.example") is None


def test_valid_status_transition_succeeds(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<msg-1@mail>")
    store.set_status(job.job_id, JobState.VALIDATING)
    store.set_status(job.job_id, JobState.QUEUED)
    updated = store.get(job.job_id)
    assert updated.status == JobState.QUEUED


def test_invalid_status_transition_rejected(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<msg-1@mail>")
    with pytest.raises(InvalidTransition):
        store.set_status(job.job_id, JobState.COMPLETED)  # can't skip straight to COMPLETED


def test_terminal_state_has_no_further_transitions(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<msg-1@mail>")
    store.set_status(job.job_id, JobState.VALIDATING)
    store.set_status(job.job_id, JobState.FAILED)
    with pytest.raises(InvalidTransition):
        store.set_status(job.job_id, JobState.QUEUED)


def test_update_persists_json_list_fields(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<msg-1@mail>")
    store.update(job.job_id, speakers=["Alice", "Bob"], unresolved_speakers=["Guest 1"])
    updated = store.get(job.job_id)
    assert updated.speakers == ["Alice", "Bob"]
    assert updated.unresolved_speakers == ["Guest 1"]


def test_existing_jobs_database_migrates_user_id_to_nullable(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    legacy_schema = SCHEMA.replace(
        "backend_user_id INTEGER,", "backend_user_id INTEGER NOT NULL,", 1
    )
    conn = sqlite3.connect(db_path)
    conn.executescript(legacy_schema)
    conn.execute(
        """INSERT INTO jobs (
            job_id, sender_email, backend_user_id, source_message_id, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        ("DIAR-2026-1001-0001", "alice@uni.ac.uk", 12, "<old@mail>", "RECEIVED", "2026-10-01"),
    )
    conn.commit()
    conn.close()

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    backend_user_column = next(
        row for row in conn.execute("PRAGMA table_info(jobs)") if row[1] == "backend_user_id"
    )
    preserved_job = conn.execute(
        "SELECT backend_user_id FROM jobs WHERE job_id = ?", ("DIAR-2026-1001-0001",)
    ).fetchone()
    conn.close()

    assert backend_user_column[3] == 0
    assert preserved_job == (12,)
    member_job = JobStore(db_path).create_job("carol@uni.ac.uk", None, "<member@mail>")
    assert member_job.backend_user_id is None


# --- ProcessedMessageStore: dedup + crash recovery ---

def test_first_begin_for_a_message_returns_true(db_path: Path):
    pm = ProcessedMessageStore(db_path)
    assert pm.begin("<msg-1@mail>", "alice@uni.ac.uk", "authorised") is True


def test_duplicate_message_after_finalization_is_skipped(db_path: Path):
    pm = ProcessedMessageStore(db_path)
    pm.begin("<msg-1@mail>", "alice@uni.ac.uk", "authorised")
    pm.finalize("<msg-1@mail>", outcome="job_created", job_id="DIAR-2026-0101-0001")

    # Same email arrives again (e.g. re-delivered, or attacker replays it) - must not reprocess.
    assert pm.begin("<msg-1@mail>", "alice@uni.ac.uk", "authorised") is False
    assert pm.get_outcome("<msg-1@mail>") == "job_created"


def test_crash_mid_processing_is_retried_up_to_limit(db_path: Path):
    pm = ProcessedMessageStore(db_path)
    # First attempt begins but never finalizes (simulating a crash).
    assert pm.begin("<msg-1@mail>", "alice@uni.ac.uk", "authorised") is True
    # Retried on subsequent polls, up to MAX_PROCESSING_ATTEMPTS.
    assert pm.begin("<msg-1@mail>", "alice@uni.ac.uk", "authorised") is True
    assert pm.begin("<msg-1@mail>", "alice@uni.ac.uk", "authorised") is True
    # Budget exhausted - stops being retried, must not be silently retried forever.
    assert pm.begin("<msg-1@mail>", "alice@uni.ac.uk", "authorised") is False


# --- Outbox ---

def test_outbox_enqueue_and_pending(db_path: Path):
    outbox = Outbox(db_path)
    outbox.enqueue(to_email="alice@uni.ac.uk", subject="Hi", body_text="Body")
    pending = outbox.pending()
    assert len(pending) == 1
    assert pending[0].to_email == "alice@uni.ac.uk"
    assert pending[0].status == "PENDING"


def test_outbox_mark_sent_removes_from_pending(db_path: Path):
    outbox = Outbox(db_path)
    outbox_id = outbox.enqueue(to_email="alice@uni.ac.uk", subject="Hi", body_text="Body")
    outbox.mark_sent(outbox_id)
    assert outbox.pending() == []


def test_outbox_mark_failed_stays_pending_for_retry_until_max_attempts(db_path: Path):
    outbox = Outbox(db_path)
    outbox_id = outbox.enqueue(to_email="alice@uni.ac.uk", subject="Hi", body_text="Body")

    outbox.mark_failed(outbox_id, "SMTP timeout", max_attempts=3)
    pending = outbox.pending()
    assert len(pending) == 1  # still retryable
    assert pending[0].last_error == "SMTP timeout"

    outbox.mark_failed(outbox_id, "SMTP timeout", max_attempts=3)
    outbox.mark_failed(outbox_id, "SMTP timeout", max_attempts=3)
    assert outbox.pending() == []  # attempts exhausted, given up
