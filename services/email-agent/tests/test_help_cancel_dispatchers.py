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
        assert sender_email == "alice@example.com"
        return self._job

    def set_status(self, job_id, new_status, **extra):
        self._job.status = new_status


def test_help_dispatcher_matches_handler_contract():
    dispatcher = CommandGraphDispatcher(None, FakeOutbox())
    outbox = dispatcher._outbox

    outcome = dispatcher.execute_help("alice@example.com", outbox, in_reply_to="reply-3", references="refs-3")

    assert isinstance(outcome, HandlerOutcome)
    assert outcome.outcome_type == "help_reply"
    assert outbox.messages[0]["to_email"] == "alice@example.com"
    assert outbox.messages[0]["subject"].startswith("What can I ask this system to do?")


def test_cancel_dispatcher_matches_handler_contract():
    job = Job(
        job_id="DIAR-2026-0919-0003",
        sender_email="alice@example.com",
        backend_user_id=12,
        source_message_id="msg-3",
        status=JobState.QUEUED,
    )
    outbox = FakeOutbox()
    store = FakeJobStore(job)

    dispatcher = CommandGraphDispatcher(store, outbox)
    outcome = dispatcher.execute_cancel(
        "DIAR-2026-0919-0003",
        "alice@example.com",
        outbox,
        in_reply_to="reply-4",
        references="refs-4",
    )

    assert isinstance(outcome, HandlerOutcome)
    assert outcome.outcome_type == "cancelled"
    assert outcome.job_id == "DIAR-2026-0919-0003"
    assert outbox.messages[0]["subject"].startswith("Cancelled — DIAR-2026-0919-0003")
