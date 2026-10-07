from pathlib import Path

from app.admin.notifier import AdminNotifier
from app.commands.schema import Operation
from app.commands.validator import ValidatedCommand
from app.diarisation.client import GroupSummary
from app.handlers import assess_query
from app.jobs.models import JobState
from app.jobs.store import JobStore, Outbox

from tests.fakes import FakeDiarisationClient


def _cmd(transcript_focus=None, github_focus=None, trello_focus=None, group_hint=None):
    return ValidatedCommand(
        operation=Operation.ASSESS_QUERY,
        group_hint=group_hint,
        transcript_focus=transcript_focus,
        github_focus=github_focus,
        trello_focus=trello_focus,
    )


# --- accept() ---


def test_accept_creates_queued_job_and_sends_ack(db_path: Path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)

    outcome = assess_query.accept(
        _cmd(transcript_focus="the API redesign"), "alice@uni.ac.uk", 12, "<msg-1@mail>",
        job_store, outbox,
    )

    assert outcome.outcome_type == "job_created"
    job = job_store.get(outcome.job_id)
    assert job.status == JobState.QUEUED
    assert job.operation == "assess_query"
    assert job.transcript_focus == "the API redesign"

    pending = outbox.pending()
    assert len(pending) == 1
    assert outcome.job_id in pending[0].body_text


# --- execute() ---


def _queued_job(db_path, group_hint=None, transcript_focus=None, github_focus=None, trello_focus=None):
    job_store = JobStore(db_path)
    job = job_store.create_job(
        "alice@uni.ac.uk", 12, "<msg-1@mail>", operation="assess_query",
        group_hint=group_hint, transcript_focus=transcript_focus,
        github_focus=github_focus, trello_focus=trello_focus,
    )
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)
    return job_store, job_store.get(job.job_id)


def test_execute_transcript_only_uses_conversation_source(db_path: Path):
    job_store, job = _queued_job(db_path, transcript_focus="the API redesign")
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    diarisation = FakeDiarisationClient(
        groups=[GroupSummary(id=1, name="Team A")],
        source_answers={"conversation": "Alice raised the API redesign on Tuesday."},
    )

    assess_query.execute(job, diarisation, job_store, outbox, admin)

    assert job_store.get(job.job_id).status == JobState.COMPLETED
    assert diarisation.queries == [("conversation", "the API redesign")]
    assert "Alice raised the API redesign on Tuesday." in outbox.pending()[0].body_text


def test_execute_no_transcript_match_says_nothing_found(db_path: Path):
    job_store, job = _queued_job(db_path, transcript_focus="something never discussed")
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    diarisation = FakeDiarisationClient(
        groups=[GroupSummary(id=1, name="Team A")], unlinked_sources={"conversation"}
    )

    assess_query.execute(job, diarisation, job_store, outbox, admin)

    assert "didn't find anything" in outbox.pending()[0].body_text.lower()


def test_execute_github_only_queries_github_source(db_path: Path):
    job_store, job = _queued_job(db_path, github_focus="open issues about the API")
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    diarisation = FakeDiarisationClient(
        groups=[GroupSummary(id=1, name="Team A")],
        source_answers={"github": "Two open issues mention the API."},
    )

    assess_query.execute(job, diarisation, job_store, outbox, admin)

    assert job_store.get(job.job_id).status == JobState.COMPLETED
    assert diarisation.queries == [("github", "open issues about the API")]
    assert "Two open issues mention the API." in outbox.pending()[0].body_text


def test_execute_github_and_trello_use_unified_query(db_path: Path):
    job_store, job = _queued_job(db_path, github_focus="open issues", trello_focus="blocked cards")
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    diarisation = FakeDiarisationClient(groups=[GroupSummary(id=1, name="Team A")])

    assess_query.execute(job, diarisation, job_store, outbox, admin)

    assert diarisation.queries == [("unified:github,trello", "open issues blocked cards")]
    assert job_store.get(job.job_id).status == JobState.COMPLETED


def test_execute_unlinked_repo_notes_unavailable_but_still_sends_transcript_answer(db_path: Path):
    job_store, job = _queued_job(
        db_path, transcript_focus="the API redesign", github_focus="open issues about the API"
    )
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    diarisation = FakeDiarisationClient(
        groups=[GroupSummary(id=1, name="Team A")],
        source_answers={"conversation": "Alice raised the API redesign on Tuesday."},
        unlinked_sources={"github"},
    )

    assess_query.execute(job, diarisation, job_store, outbox, admin)

    assert job_store.get(job.job_id).status == JobState.COMPLETED
    body = outbox.pending()[0].body_text
    assert "Alice raised the API redesign on Tuesday." in body
    assert "doesn't have a GitHub repo linked" in body


def test_execute_ambiguous_group_asks_for_clarification(db_path: Path):
    job_store, job = _queued_job(db_path, transcript_focus="anything")
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    diarisation = FakeDiarisationClient(
        groups=[GroupSummary(id=1, name="Team A"), GroupSummary(id=2, name="Team B")]
    )

    assess_query.execute(job, diarisation, job_store, outbox, admin)

    updated = job_store.get(job.job_id)
    assert updated.status == JobState.NEEDS_CLARIFICATION
    body = outbox.pending()[0].body_text
    assert "Team A" in body and "Team B" in body


def test_execute_all_sources_fail_marks_job_failed_and_alerts_admin(db_path: Path):
    job_store, job = _queued_job(db_path, transcript_focus="the API redesign")
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email="admin@uni.ac.uk")
    diarisation = FakeDiarisationClient(
        groups=[GroupSummary(id=1, name="Team A")], fail_on="query_conversation"
    )

    assess_query.execute(job, diarisation, job_store, outbox, admin)

    updated = job_store.get(job.job_id)
    assert updated.status == JobState.FAILED
    pending = outbox.pending()
    assert len(pending) == 2  # sender failure email + admin alert
    recipients = {m.to_email for m in pending}
    assert "alice@uni.ac.uk" in recipients
    assert "admin@uni.ac.uk" in recipients


def test_execute_backend_login_failure_marks_job_failed(db_path: Path):
    job_store, job = _queued_job(db_path, transcript_focus="anything")
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    diarisation = FakeDiarisationClient(groups=[GroupSummary(id=1, name="Team A")], fail_on="login")

    assess_query.execute(job, diarisation, job_store, outbox, admin)

    assert job_store.get(job.job_id).status == JobState.FAILED


def test_execute_records_backend_job_id_and_stops_quietly_when_cancelled(db_path: Path):
    job_store, job = _queued_job(db_path, transcript_focus="the API redesign")
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    diarisation = FakeDiarisationClient(groups=[GroupSummary(id=1, name="Team A")])

    assess_query.execute(job, diarisation, job_store, outbox, admin)

    assert job_store.get(job.job_id).backend_job_id == "backend-job-1"
    assert job_store.get(job.job_id).status == JobState.COMPLETED


def test_execute_cancelled_backend_job_marks_job_cancelled_and_sends_nothing(db_path: Path):
    job_store, job = _queued_job(db_path, transcript_focus="the API redesign")
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email="admin@uni.ac.uk")
    diarisation = FakeDiarisationClient(groups=[GroupSummary(id=1, name="Team A")])
    diarisation.cancel_queries = True

    assess_query.execute(job, diarisation, job_store, outbox, admin)

    assert job_store.get(job.job_id).status == JobState.CANCELLED
    assert outbox.pending() == []
