from __future__ import annotations

from app.commands.validator import ValidatedCommand
from app.email_templates.render import render_cancelled, render_cannot_cancel
from app.handlers.base import STATUS_TEXT, ClarificationRequired, HandlerOutcome
from app.jobs.models import JobState
from app.jobs.store import JobStore, Outbox

# Only jobs that haven't been dispatched to the backend yet can be cancelled - once a Meeting
# has been created / a file uploaded there, there's nothing safe to roll back (spec decision:
# no destructive deletes).
_CANCELLABLE_STATES = {JobState.QUEUED, JobState.NEEDS_CLARIFICATION}


def handle(
    validated_cmd: ValidatedCommand, sender_email: str, job_store: JobStore, outbox: Outbox,
    in_reply_to: str | None = None, references: str | None = None,
) -> HandlerOutcome:
    job = job_store.get_owned(validated_cmd.job_id, sender_email)
    if job is None:
        raise ClarificationRequired(
            f"I couldn't find a job {validated_cmd.job_id} associated with your account."
        )

    if job.status in _CANCELLABLE_STATES:
        job_store.set_status(job.job_id, JobState.CANCELLED)
        subject, body = render_cancelled(job.job_id)
        outbox.enqueue(
            to_email=sender_email, subject=subject, body_text=body, job_id=job.job_id,
            in_reply_to=in_reply_to, references=references,
        )
        return HandlerOutcome("cancelled", job.job_id)

    status_text = STATUS_TEXT.get(job.status, job.status.value)
    subject, body = render_cannot_cancel(job.job_id, status_text)
    outbox.enqueue(
        to_email=sender_email, subject=subject, body_text=body, job_id=job.job_id,
        in_reply_to=in_reply_to, references=references,
    )
    return HandlerOutcome("cannot_cancel", job.job_id)
