from datetime import datetime, timezone

from app.diarisation.client import GroupSummary
from app.jobs.models import JobState
from app.jobs.store import JobStore, Outbox, PendingClarificationStore
from app.admin.notifier import AdminNotifier
from app.handlers import log_meeting
from app.llm.log_meeting_graph import build_log_meeting_graph

from tests.fakes import FakeDiarisationClient


def test_log_meeting_graph_creates_meeting_and_saves_outline_as_comment():
    client = FakeDiarisationClient(groups=[GroupSummary(id=7, name="Team A")])
    graph = build_log_meeting_graph(client)

    result = graph.invoke(
        {
            "job_id": "DIAR-2026-1002-0001",
            "sender_email": "alice@example.com",
            "group_hint": "Team A",
            "meeting_date": "2026-10-01T10:00:00+00:00",
            "comment_text": "Decisions: proceed with the pilot.",
        }
    )

    assert result["group_id"] == 7
    assert result["group_name"] == "Team A"
    assert result["meeting_id"] == 1
    assert client.comments == [(7, 1, "Decisions: proceed with the pilot.")]
    assert [event["event"] for event in result["audit_events"]][-2:] == [
        "meeting_created",
        "meeting_notes_saved",
    ]


def test_log_meeting_handler_completes_and_queues_confirmation(db_path, tmp_path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    job = job_store.create_job(
        "alice@example.com",
        12,
        "<message@example.com>",
        operation="log_meeting",
        group_hint="Team A",
        meeting_date=datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat(),
        comment_text="Decisions: proceed with the pilot.",
    )
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)
    client = FakeDiarisationClient(groups=[GroupSummary(id=7, name="Team A")])
    admin = AdminNotifier(db_path, outbox, admin_email=None)

    log_meeting.execute(job_store.get(job.job_id), client, job_store, outbox, admin)

    updated = job_store.get(job.job_id)
    assert updated.status == JobState.COMPLETED
    assert updated.resolved_group_id == 7
    assert updated.backend_meeting_id == client.meetings[0].id
    assert client.comments == [(7, client.meetings[0].id, "Decisions: proceed with the pilot.")]
    assert len(outbox.pending()) == 1
    assert "Meeting notes saved" in outbox.pending()[0].body_text


def test_log_meeting_handler_persists_group_clarification(db_path, tmp_path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    pending_clarifications = PendingClarificationStore(db_path)
    job = job_store.create_job(
        "alice@example.com",
        12,
        "<message@example.com>",
        operation="log_meeting",
        meeting_date=datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat(),
        comment_text="Decisions: proceed with the pilot.",
        original_subject="Project planning notes",
        original_body_text="We discussed the launch timeline and owners.",
    )
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    client = FakeDiarisationClient(
        groups=[GroupSummary(id=7, name="Team A"), GroupSummary(id=8, name="Team B")]
    )

    log_meeting.execute(
        job_store.get(job.job_id),
        client,
        job_store,
        outbox,
        admin,
        pending_clarifications=pending_clarifications,
    )

    updated = job_store.get(job.job_id)
    clarification = pending_clarifications.get(job.job_id)
    assert updated.status == JobState.NEEDS_CLARIFICATION
    assert clarification.expected_field == "group_hint"
    assert clarification.options == ["Team A", "Team B"]
    assert outbox.pending()[0].subject.startswith(
        "Re: Project planning notes [Clarification needed | DIAR-"
    )
    assert "> We discussed the launch timeline and owners." in outbox.pending()[0].body_text
    assert client.meetings == []
    assert client.comments == []


def test_log_meeting_comment_failure_keeps_created_meeting_id(db_path, tmp_path):
    job_store = JobStore(db_path)
    outbox = Outbox(db_path)
    job = job_store.create_job(
        "alice@example.com",
        12,
        "<message@example.com>",
        operation="log_meeting",
        group_hint="Team A",
        meeting_date=datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat(),
        comment_text="Decisions: proceed with the pilot.",
    )
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)
    client = FakeDiarisationClient(
        groups=[GroupSummary(id=7, name="Team A")], fail_on="add_comment"
    )
    admin = AdminNotifier(db_path, outbox, admin_email=None)

    log_meeting.execute(job_store.get(job.job_id), client, job_store, outbox, admin)

    updated = job_store.get(job.job_id)
    assert updated.status == JobState.FAILED
    assert updated.backend_meeting_id == client.meetings[0].id
    assert len(outbox.pending()) == 1
    assert "could not process" in outbox.pending()[0].subject.lower()