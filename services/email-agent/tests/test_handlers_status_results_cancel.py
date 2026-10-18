from pathlib import Path

import pytest

from app.commands.schema import Operation
from app.commands.validator import ValidatedCommand
from app.handlers import cancel, help as help_handler, results, status
from app.handlers.base import ClarificationRequired
from app.jobs.models import JobState
from app.jobs.store import JobStore, Outbox


def _cmd(operation, job_id, return_statistics=False):
    return ValidatedCommand(operation=operation, job_id=job_id, return_statistics=return_statistics)


def test_status_reports_current_state(db_path: Path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    job = job_store.create_job("alice@uni.ac.uk", 12, "<msg@mail>")
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)

    outcome = status.handle(_cmd(Operation.STATUS, job.job_id), "alice@uni.ac.uk", job_store, outbox)

    assert outcome.outcome_type == "status_reply"
    pending = outbox.pending()
    assert "Queued" in pending[0].body_text


def test_results_before_completion_has_no_attachment(db_path: Path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    job = job_store.create_job("alice@uni.ac.uk", 12, "<msg@mail>")
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)

    results.handle(_cmd(Operation.RESULTS, job.job_id), "alice@uni.ac.uk", job_store, outbox)

    pending = outbox.pending()
    assert pending[0].attachments == []


def test_results_after_completion_lists_attendees(db_path: Path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    job = job_store.create_job("alice@uni.ac.uk", 12, "<msg@mail>")
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)
    job_store.set_status(job.job_id, JobState.PROCESSING)
    job_store.update(job.job_id, resolved_attendees=["Alice"], unresolved_speakers=["Guest 1"])
    job_store.set_status(job.job_id, JobState.COMPLETED)

    results.handle(_cmd(Operation.RESULTS, job.job_id), "alice@uni.ac.uk", job_store, outbox)

    pending = outbox.pending()
    assert "Alice" in pending[0].body_text
    assert "Guest 1" in pending[0].body_text


def test_cancel_queued_job_succeeds(db_path: Path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    job = job_store.create_job("alice@uni.ac.uk", 12, "<msg@mail>")
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)

    outcome = cancel.handle(_cmd(Operation.CANCEL, job.job_id), "alice@uni.ac.uk", job_store, outbox)

    assert outcome.outcome_type == "cancelled"
    assert job_store.get(job.job_id).status == JobState.CANCELLED


def test_cancel_completed_job_is_refused(db_path: Path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    job = job_store.create_job("alice@uni.ac.uk", 12, "<msg@mail>")
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)
    job_store.set_status(job.job_id, JobState.PROCESSING)
    job_store.set_status(job.job_id, JobState.COMPLETED)

    outcome = cancel.handle(_cmd(Operation.CANCEL, job.job_id), "alice@uni.ac.uk", job_store, outbox)

    assert outcome.outcome_type == "cannot_cancel"
    assert job_store.get(job.job_id).status == JobState.COMPLETED  # unchanged
    pending = outbox.pending()
    assert "already been processed" in pending[0].body_text.lower()


def test_status_for_job_deleted_between_validation_and_handling_raises_clarification(db_path: Path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    with pytest.raises(ClarificationRequired):
        status.handle(_cmd(Operation.STATUS, "DIAR-2026-0101-9999"), "alice@uni.ac.uk", job_store, outbox)


def test_help_sends_static_reply_with_no_job(db_path: Path):
    outbox = Outbox(db_path)
    outcome = help_handler.handle("alice@uni.ac.uk", outbox)
    assert outcome.outcome_type == "help_reply"
    pending = outbox.pending()
    assert pending[0].job_id is None


def _processing_job(job_store, **fields):
    job = job_store.create_job("alice@uni.ac.uk", 12, "<msg@mail>", **fields)
    for state in (JobState.VALIDATING, JobState.QUEUED, JobState.PROCESSING):
        job_store.set_status(job.job_id, state)
    return job


def test_status_includes_backend_transcript_processing_progress(db_path: Path):
    from app.diarisation.client import BackendJob
    from tests.fakes import FakeDiarisationClient

    job_store, outbox = JobStore(db_path), Outbox(db_path)
    job = _processing_job(job_store, backend_meeting_id=42)
    backend = FakeDiarisationClient(groups=[])
    backend.backend_jobs["b1"] = BackendJob(
        "b1", "transcript_processing", "running", progress="summarising meeting", meeting_id=42
    )

    status.handle(
        _cmd(Operation.STATUS, job.job_id), "alice@uni.ac.uk", job_store, outbox, diarisation_client=backend
    )

    body = outbox.pending()[0].body_text
    assert "Transcript indexing and summarising: running (summarising meeting)" in body


def test_status_still_answers_when_the_backend_is_unreachable(db_path: Path):
    from tests.fakes import FakeDiarisationClient

    job_store, outbox = JobStore(db_path), Outbox(db_path)
    job = _processing_job(job_store, backend_job_id="b1")
    backend = FakeDiarisationClient(groups=[], fail_on="get_job")

    outcome = status.handle(
        _cmd(Operation.STATUS, job.job_id), "alice@uni.ac.uk", job_store, outbox, diarisation_client=backend
    )

    assert outcome.outcome_type == "status_reply"
    assert "Currently being processed" in outbox.pending()[0].body_text


def test_cancel_stops_the_backend_job_for_a_processing_query(db_path: Path):
    from app.diarisation.client import BackendJob
    from tests.fakes import FakeDiarisationClient

    job_store, outbox = JobStore(db_path), Outbox(db_path)
    job = _processing_job(job_store, operation="assess_query", backend_job_id="b1")
    backend = FakeDiarisationClient(groups=[])
    backend.backend_jobs["b1"] = BackendJob("b1", "query", "running")

    outcome = cancel.handle(
        _cmd(Operation.CANCEL, job.job_id), "alice@uni.ac.uk", job_store, outbox, diarisation_client=backend
    )

    assert outcome.outcome_type == "cancelled"
    assert backend.cancelled_backend_jobs == ["b1"]
    assert job_store.get(job.job_id).status == JobState.CANCELLED


def test_cancel_of_processing_job_without_backend_job_is_refused(db_path: Path):
    from tests.fakes import FakeDiarisationClient

    job_store, outbox = JobStore(db_path), Outbox(db_path)
    job = _processing_job(job_store)

    outcome = cancel.handle(
        _cmd(Operation.CANCEL, job.job_id), "alice@uni.ac.uk", job_store, outbox,
        diarisation_client=FakeDiarisationClient(groups=[]),
    )

    assert outcome.outcome_type == "cannot_cancel"
