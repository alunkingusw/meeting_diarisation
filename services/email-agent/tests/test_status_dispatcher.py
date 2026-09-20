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
        assert job_id == "DIAR-2026-0919-0001"
        assert sender_email == "alice@example.com"
        return self._job


def test_status_dispatcher_uses_graph_and_preserves_handler_contract():
    job = Job(
        job_id="DIAR-2026-0919-0001",
        sender_email="alice@example.com",
        backend_user_id=12,
        source_message_id="msg-1",
        status=JobState.QUEUED,
    )
    outbox = FakeOutbox()
    store = FakeJobStore(job)

    dispatcher = CommandGraphDispatcher(store, outbox)
    outcome = dispatcher.execute_status(
        "DIAR-2026-0919-0001",
        "alice@example.com",
        outbox,
        in_reply_to="reply-1",
        references="refs-1",
    )

    assert isinstance(outcome, HandlerOutcome)
    assert outcome.outcome_type == "status_reply"
    assert outcome.job_id == "DIAR-2026-0919-0001"
    assert outbox.messages[0]["to_email"] == "alice@example.com"
    assert outbox.messages[0]["job_id"] == "DIAR-2026-0919-0001"
