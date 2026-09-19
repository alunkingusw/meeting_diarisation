from __future__ import annotations

from app.commands.validator import ValidatedCommand
from app.email_templates.render import render_status
from app.handlers.base import STATUS_TEXT, ClarificationRequired, HandlerOutcome
from app.jobs.store import JobStore, Outbox


def handle(
    validated_cmd: ValidatedCommand, sender_email: str, job_store: JobStore, outbox: Outbox,
    in_reply_to: str | None = None, references: str | None = None,
) -> HandlerOutcome:
    job = job_store.get_owned(validated_cmd.job_id, sender_email)
    if job is None:
        # The validator already confirmed ownership moments earlier; re-checking here guards
        # against the job being deleted/altered between validation and execution.
        raise ClarificationRequired(
            f"I couldn't find a job {validated_cmd.job_id} associated with your account."
        )

    status_text = STATUS_TEXT.get(job.status, job.status.value)
    subject, body = render_status(job.job_id, status_text)
    outbox.enqueue(
        to_email=sender_email, subject=subject, body_text=body, job_id=job.job_id,
        in_reply_to=in_reply_to, references=references,
    )
    return HandlerOutcome("status_reply", job.job_id)
