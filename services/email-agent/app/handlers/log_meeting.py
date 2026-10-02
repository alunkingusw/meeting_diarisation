"""Creates a transcript-free meeting from an email and saves its notes as a comment."""
from __future__ import annotations

import logging
from typing import Optional

from app.admin.notifier import AdminCategory, AdminNotifier
from app.commands.validator import ValidatedCommand
from app.diarisation.client import DiarisationApiError, DiarisationClient
from app.email_templates.render import render_clarification, render_failure, render_meeting_log_confirmation
from app.handlers.base import HandlerOutcome
from app.jobs.models import Job, JobState
from app.jobs.store import JobStore, Outbox, PendingClarificationStore
from app.llm.log_meeting_graph import build_log_meeting_graph

logger = logging.getLogger(__name__)


def accept(
    validated_cmd: ValidatedCommand,
    sender_email: str,
    backend_user_id: int | None,
    source_message_id: str,
    job_store: JobStore,
    outbox: Outbox,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    original_subject: Optional[str] = None,
    original_body_text: Optional[str] = None,
) -> HandlerOutcome:
    assert validated_cmd.meeting_date is not None
    assert validated_cmd.comment is not None

    job = job_store.create_job(
        sender_email,
        backend_user_id,
        source_message_id,
        operation="log_meeting",
        group_hint=validated_cmd.group_hint,
        meeting_date=validated_cmd.meeting_date.isoformat(),
        meeting_date_source="email_text",
        comment_text=validated_cmd.comment,
        in_reply_to_message_id=in_reply_to,
        original_subject=original_subject,
        original_body_text=original_body_text,
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
    pending_clarifications: Optional[PendingClarificationStore] = None,
) -> None:
    pending_clarifications = pending_clarifications or PendingClarificationStore(job_store._db_path)
    parent_message_id = job.in_reply_to_message_id or job.source_message_id
    try:
        job_store.set_status(job.job_id, JobState.PROCESSING)
        graph = build_log_meeting_graph(diarisation_client)
        result = graph.invoke(
            {
                "job_id": job.job_id,
                "sender_email": job.sender_email,
                "group_hint": job.group_hint,
                "meeting_date": job.meeting_date,
                "comment_text": job.comment_text,
            }
        )
        logger.info(
            "Job %s log-meeting graph steps: %s", job.job_id,
            [e["event"] for e in result.get("audit_events", [])],
        )

        if result.get("clarification_question"):
            question = result["clarification_question"]
            job_store.set_status(job.job_id, JobState.NEEDS_CLARIFICATION)
            pending_clarifications.put(
                job.job_id,
                question,
                result.get("clarification_expected_field", "group_hint"),
                result.get("clarification_options", []),
            )
            subject, body = render_clarification(
                question, job.job_id, job.original_subject, job.original_body_text
            )
            outbox.enqueue(
                to_email=job.sender_email,
                subject=subject,
                body_text=body,
                job_id=job.job_id,
                in_reply_to=parent_message_id,
                references=parent_message_id,
            )
            return

        job_store.update(
            job.job_id,
            resolved_group_id=result["group_id"],
            resolved_group_name=result["group_name"],
            backend_meeting_id=result["meeting_id"],
        )
        if result.get("execution_error"):
            raise RuntimeError(result["execution_error"])
        job_store.set_status(job.job_id, JobState.COMPLETED)

        subject, body = render_meeting_log_confirmation(
            job.job_id,
            result["group_name"],
            job.meeting_date,
            result["meeting_id"],
            job.comment_text,
        )
        outbox.enqueue(
            to_email=job.sender_email,
            subject=subject,
            body_text=body,
            job_id=job.job_id,
            in_reply_to=parent_message_id,
            references=parent_message_id,
        )
    except DiarisationApiError as exc:
        logger.exception("Backend API error logging meeting for job %s", job.job_id)
        _fail(job, str(exc), job_store, outbox, admin_notifier, parent_message_id)
    except Exception as exc:
        logger.exception("Unexpected error logging meeting for job %s", job.job_id)
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
        f"Meeting log job {job.job_id} failed.",
        detail={"job_id": job.job_id, "reason": reason},
    )