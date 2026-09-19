"""Queues and executes comments on an existing backend meeting."""
from __future__ import annotations

import logging
from typing import Optional

from app.admin.notifier import AdminCategory, AdminNotifier
from app.commands.validator import ValidatedCommand
from app.diarisation.client import DiarisationApiError, DiarisationClient
from app.email_templates.render import render_comment_confirmation, render_failure
from app.handlers.base import HandlerOutcome
from app.jobs.models import Job, JobState
from app.jobs.store import JobStore, Outbox

logger = logging.getLogger(__name__)


def accept(
    validated_cmd: ValidatedCommand,
    sender_email: str,
    backend_user_id: int,
    source_message_id: str,
    job_store: JobStore,
    outbox: Outbox,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> HandlerOutcome:
    job = job_store.create_job(
        sender_email,
        backend_user_id,
        source_message_id,
        operation="add_comment",
        resolved_group_id=validated_cmd.group_id,
        backend_meeting_id=validated_cmd.meeting_id,
        comment_text=validated_cmd.comment,
        in_reply_to_message_id=in_reply_to,
    )
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)
    return HandlerOutcome("job_created", job.job_id)


def execute(
    job: Job,
    diarisation_client: DiarisationClient,
    job_store: JobStore,
    outbox: Outbox,
    admin_notifier: AdminNotifier,
) -> None:
    parent_message_id = job.in_reply_to_message_id or job.source_message_id
    try:
        job_store.set_status(job.job_id, JobState.PROCESSING)
        token = diarisation_client.login_for_email(job.sender_email)
        result = diarisation_client.add_comment(
            token, job.resolved_group_id, job.backend_meeting_id, job.comment_text
        )
        job_store.set_status(job.job_id, JobState.COMPLETED)
        subject, body = render_comment_confirmation(job.job_id, result)
        outbox.enqueue(
            to_email=job.sender_email,
            subject=subject,
            body_text=body,
            job_id=job.job_id,
            in_reply_to=parent_message_id,
            references=parent_message_id,
        )
    except DiarisationApiError as exc:
        _fail(job, str(exc), job_store, outbox, admin_notifier, parent_message_id)
    except Exception as exc:
        logger.exception("Unexpected error adding comment for job %s", job.job_id)
        _fail(job, f"Unexpected error: {exc}", job_store, outbox, admin_notifier, parent_message_id)


def _fail(
    job: Job,
    reason: str,
    job_store: JobStore,
    outbox: Outbox,
    admin_notifier: AdminNotifier,
    parent_message_id: str,
) -> None:
    job_store.set_status(job.job_id, JobState.FAILED, error=reason)
    subject, body = render_failure(reason, job.job_id)
    outbox.enqueue(
        to_email=job.sender_email,
        subject=subject,
        body_text=body,
        job_id=job.job_id,
        in_reply_to=parent_message_id,
        references=parent_message_id,
    )
    admin_notifier.alert(
        AdminCategory.BACKEND_COMMENT_FAILURE,
        f"Comment job {job.job_id} failed.",
        detail={"job_id": job.job_id, "reason": reason},
    )