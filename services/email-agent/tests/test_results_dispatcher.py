from app.commands.validator import ValidatedCommand
from app.handlers.base import HandlerOutcome
from app.jobs.models import Job, JobState
from app.llm.command_dispatcher import CommandGraphDispatcher


class FakeOutbox:
    def __init__(self):
        self.messages = []

    def enqueue(self, **kwargs):
        self.messages.append(kwargs)


class FakeJobStore:
    def __init__(self, job):
        self._job = job

    def get_owned(self, job_id, sender_email):
        assert job_id == "DIAR-2026-0919-0002"
        assert sender_email == "alice@example.com"
        return self._job


def test_results_dispatcher_matches_handler_contract():
    job = Job(
        job_id="DIAR-2026-0919-0002",
        sender_email="alice@example.com",
        backend_user_id=12,
        source_message_id="msg-2",
        status=JobState.COMPLETED,
        resolved_group_name="Team A",
        meeting_date="2026-09-19",
        resolved_attendees=[{"name": "Alice"}],
        unresolved_speakers=[],
    )
    outbox = FakeOutbox()
    store = FakeJobStore(job)

    dispatcher = CommandGraphDispatcher(store, outbox)
    outcome = dispatcher.execute_results(
        "DIAR-2026-0919-0002",
        "alice@example.com",
        outbox,
        in_reply_to="reply-2",
        references="refs-2",
    )

    assert isinstance(outcome, HandlerOutcome)
    assert outcome.outcome_type == "results_reply"
    assert outcome.job_id == "DIAR-2026-0919-0002"
    assert outbox.messages[0]["to_email"] == "alice@example.com"
    assert outbox.messages[0]["subject"].startswith("Results for DIAR-2026-0919-0002")
