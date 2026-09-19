from __future__ import annotations

from pathlib import Path

from app.commands.validator import ValidatedCommand
from app.email_templates.render import render_results
from app.handlers.base import STATUS_TEXT, ClarificationRequired, HandlerOutcome
from app.jobs.models import JobState
from app.jobs.store import JobStore, Outbox


def handle(
    validated_cmd: ValidatedCommand, sender_email: str, job_store: JobStore, outbox: Outbox,
    in_reply_to: str | None = None, references: str | None = None,
) -> HandlerOutcome:
    job = job_store.get_owned(validated_cmd.job_id, sender_email)
    if job is None:
        raise ClarificationRequired(
            f"I couldn't find a job {validated_cmd.job_id} associated with your account."
        )

    status_text = STATUS_TEXT.get(job.status, job.status.value)
    is_completed = job.status == JobState.COMPLETED

    subject, body = render_results(
        job.job_id,
        status_text,
        group_name=job.resolved_group_name,
        meeting_date=job.meeting_date,
        resolved_attendees=job.resolved_attendees if is_completed else None,
        unresolved_speakers=job.unresolved_speakers if is_completed else None,
    )

    attachments = None
    if is_completed and job.attachment_storage_path and Path(job.attachment_storage_path).exists():
        attachments = [job.attachment_storage_path]

    outbox.enqueue(
        to_email=sender_email,
        subject=subject,
        body_text=body,
        job_id=job.job_id,
        attachments=attachments,
        in_reply_to=in_reply_to,
        references=references,
    )
    return HandlerOutcome("results_reply", job.job_id)
