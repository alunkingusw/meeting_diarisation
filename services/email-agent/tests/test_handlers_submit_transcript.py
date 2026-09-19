from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.admin.notifier import AdminNotifier
from app.commands.schema import Operation
from app.commands.validator import AttachmentMeta, ValidatedCommand
from app.diarisation.client import GroupSummary
from app.handlers import submit_transcript
from app.jobs.models import JobState
from app.jobs.store import JobStore, Outbox
from app.mail.base import Attachment
from app.settings import StorageSettings

from tests.fakes import FakeDiarisationClient

FIXTURES = Path(__file__).parent / "fixtures" / "vtt"


def _storage(tmp_path: Path) -> StorageSettings:
    return StorageSettings(
        incoming=tmp_path / "incoming",
        processing=tmp_path / "processing",
        completed=tmp_path / "completed",
        failed=tmp_path / "failed",
        db_path=tmp_path / "unused.db",
    )


def _attachment(fixture_name: str, filename: str = "meeting.vtt") -> Attachment:
    content = (FIXTURES / fixture_name).read_bytes()
    return Attachment(filename=filename, content_type="text/vtt", content=content)


def _validated_cmd(filename="meeting.vtt", size=100, group_hint=None, mentioned_date=None):
    return ValidatedCommand(
        operation=Operation.SUBMIT_TRANSCRIPT,
        attachment=AttachmentMeta(filename=filename, size_bytes=size, content_type="text/vtt"),
        group_hint=group_hint,
        mentioned_date=mentioned_date,
    )


# --- accept() ---

def test_accept_valid_vtt_creates_queued_job_and_sends_ack(db_path: Path, tmp_path: Path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    storage = _storage(tmp_path)
    attachment = _attachment("valid_with_date.vtt")

    outcome = submit_transcript.accept(
        [attachment],
        _validated_cmd(),
        "alice@uni.ac.uk",
        12,
        "<msg-1@mail>",
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        job_store,
        outbox,
        storage,
    )

    assert outcome.outcome_type == "job_created"
    job = job_store.get(outcome.job_id)
    assert job.status == JobState.QUEUED
    assert job.speakers == ["Alice", "Bob"]
    assert job.meeting_date_source == "vtt_note"
    assert job.meeting_date.startswith("2026-08-11")

    pending = outbox.pending()
    assert len(pending) == 1
    assert pending[0].to_email == "alice@uni.ac.uk"
    assert outcome.job_id in pending[0].subject


def test_accept_falls_back_to_received_time_when_no_date_anywhere(db_path: Path, tmp_path: Path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    storage = _storage(tmp_path)
    attachment = _attachment("valid_no_date.vtt")
    received = datetime(2025, 3, 4, 12, 0, tzinfo=timezone.utc)

    outcome = submit_transcript.accept(
        [attachment], _validated_cmd(), "alice@uni.ac.uk", 12, "<msg-1@mail>", received,
        job_store, outbox, storage,
    )
    job = job_store.get(outcome.job_id)
    assert job.meeting_date_source == "received_timestamp"
    assert job.meeting_date.startswith("2025-03-04")


def test_accept_uses_mentioned_date_when_no_vtt_note(db_path: Path, tmp_path: Path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    storage = _storage(tmp_path)
    attachment = _attachment("valid_no_date.vtt")

    outcome = submit_transcript.accept(
        [attachment],
        _validated_cmd(mentioned_date="11 August 2026"),
        "alice@uni.ac.uk", 12, "<msg-1@mail>",
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        job_store, outbox, storage,
    )
    job = job_store.get(outcome.job_id)
    assert job.meeting_date_source == "email_text"
    assert job.meeting_date.startswith("2026-08-11")


def test_accept_rejects_invalid_vtt_content_and_moves_to_failed(db_path: Path, tmp_path: Path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    storage = _storage(tmp_path)
    attachment = _attachment("no_cues.vtt")

    outcome = submit_transcript.accept(
        [attachment], _validated_cmd(), "alice@uni.ac.uk", 12, "<msg-1@mail>",
        datetime(2025, 1, 1, tzinfo=timezone.utc), job_store, outbox, storage,
    )

    assert outcome.outcome_type == "rejected"
    job = job_store.get(outcome.job_id)
    assert job.status == JobState.FAILED
    assert Path(job.attachment_storage_path).parent == storage.failed

    pending = outbox.pending()
    assert len(pending) == 1
    assert "vtt transcript" in pending[0].body_text.lower()


# --- execute() ---

def _job_store_with_queued_job(db_path, tmp_path, group_hint=None, speakers=None):
    job_store = JobStore(db_path)
    storage = _storage(tmp_path)
    storage.incoming.mkdir(parents=True, exist_ok=True)
    stored_path = storage.incoming / "abc123_meeting.vtt"
    stored_path.write_text("WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\nAlice: hi\n")

    job = job_store.create_job(
        "alice@uni.ac.uk", 12, "<msg-1@mail>", operation="submit_transcript",
        group_hint=group_hint,
        attachment_filename="meeting.vtt",
        attachment_storage_path=str(stored_path),
        meeting_date=datetime(2026, 8, 11, tzinfo=timezone.utc).isoformat(),
        meeting_date_source="vtt_note",
        speakers=speakers or ["Alice", "Bob"],
    )
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)
    return job_store, storage, job_store.get(job.job_id)


def test_execute_happy_path_single_group_completes_and_adds_attendees(db_path: Path, tmp_path: Path):
    job_store, storage, job = _job_store_with_queued_job(db_path, tmp_path)
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    fake_client = FakeDiarisationClient(
        groups=[GroupSummary(id=1, name="Team A")],
        member_by_name={"Alice": 101, "Bob": None},
    )

    submit_transcript.execute(job, fake_client, job_store, outbox, admin, storage)

    updated = job_store.get(job.job_id)
    assert updated.status == JobState.COMPLETED
    assert updated.resolved_group_name == "Team A"
    assert updated.resolved_attendees == ["Alice"]
    assert updated.unresolved_speakers == ["Bob"]
    assert fake_client.attendees_added == [101]
    assert Path(updated.attachment_storage_path).parent == storage.completed

    pending = outbox.pending()
    assert len(pending) == 1
    assert "Alice" in pending[0].body_text
    assert "Bob" in pending[0].body_text


def test_execute_group_hint_matches_case_insensitively(db_path: Path, tmp_path: Path):
    job_store, storage, job = _job_store_with_queued_job(db_path, tmp_path, group_hint="team a")
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    fake_client = FakeDiarisationClient(
        groups=[GroupSummary(id=1, name="Team A"), GroupSummary(id=2, name="Team B")],
        member_by_name={"Alice": 101, "Bob": 102},
    )

    submit_transcript.execute(job, fake_client, job_store, outbox, admin, storage)

    updated = job_store.get(job.job_id)
    assert updated.status == JobState.COMPLETED
    assert updated.resolved_group_id == 1


def test_execute_ambiguous_group_with_no_hint_asks_for_clarification(db_path: Path, tmp_path: Path):
    job_store, storage, job = _job_store_with_queued_job(db_path, tmp_path, group_hint=None)
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    fake_client = FakeDiarisationClient(
        groups=[GroupSummary(id=1, name="Team A"), GroupSummary(id=2, name="Team B")],
    )

    submit_transcript.execute(job, fake_client, job_store, outbox, admin, storage)

    updated = job_store.get(job.job_id)
    assert updated.status == JobState.NEEDS_CLARIFICATION
    pending = outbox.pending()
    assert "Team A" in pending[0].body_text
    assert "Team B" in pending[0].body_text


def test_execute_unmatched_group_hint_asks_for_clarification(db_path: Path, tmp_path: Path):
    job_store, storage, job = _job_store_with_queued_job(db_path, tmp_path, group_hint="Nonexistent Group")
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    fake_client = FakeDiarisationClient(groups=[GroupSummary(id=1, name="Team A")])

    submit_transcript.execute(job, fake_client, job_store, outbox, admin, storage)

    updated = job_store.get(job.job_id)
    assert updated.status == JobState.NEEDS_CLARIFICATION


def test_execute_backend_failure_marks_job_failed_and_alerts_admin(db_path: Path, tmp_path: Path):
    job_store, storage, job = _job_store_with_queued_job(db_path, tmp_path)
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email="admin@uni.ac.uk")
    fake_client = FakeDiarisationClient(groups=[GroupSummary(id=1, name="Team A")], fail_on="login")

    submit_transcript.execute(job, fake_client, job_store, outbox, admin, storage)

    updated = job_store.get(job.job_id)
    assert updated.status == JobState.FAILED
    assert Path(updated.attachment_storage_path).parent == storage.failed

    pending = outbox.pending()
    assert len(pending) == 2  # sender failure email + admin alert
    recipients = {m.to_email for m in pending}
    assert "alice@uni.ac.uk" in recipients
    assert "admin@uni.ac.uk" in recipients
