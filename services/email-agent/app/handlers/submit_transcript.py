"""The only operation that touches the backend. Split into accept() (local-only: validate,
save, create the job, done inline in the mail-polling pipeline) and execute() (all backend HTTP
calls, run by the job worker thread) so a slow/unavailable backend never blocks mail polling.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dateutil import parser as dateutil_parser

from app.admin.notifier import AdminCategory, AdminNotifier
from app.commands.validator import ValidatedCommand
from app.diarisation.client import DiarisationApiError, DiarisationClient
from app.email_templates.render import render_ack, render_clarification, render_completion, render_failure
from app.handlers.base import HandlerOutcome
from app.jobs.models import Job, JobState
from app.jobs.store import JobStore, Outbox, PendingClarificationStore
from app.llm.submit_transcript_graph import build_submit_transcript_graph
from app.mail.base import Attachment
from app.settings import StorageSettings
from app.storage.attachments import move_to, save_incoming
from app.vtt.parser import ParsedVtt, VttParseError, parse_vtt

logger = logging.getLogger(__name__)


def accept(
    email_attachments: list[Attachment],
    validated_cmd: ValidatedCommand,
    sender_email: str,
    backend_user_id: int | None,
    source_message_id: str,
    received_at: datetime,
    job_store: JobStore,
    outbox: Outbox,
    storage: StorageSettings,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    pending_clarifications: Optional[PendingClarificationStore] = None,
    original_subject: Optional[str] = None,
    original_body_text: Optional[str] = None,
) -> HandlerOutcome:
    pending_clarifications = pending_clarifications or PendingClarificationStore(job_store._db_path)
    assert validated_cmd.attachment is not None  # guaranteed by the validator

    real_attachment = next(
        (a for a in email_attachments if a.filename == validated_cmd.attachment.filename), None
    )
    assert real_attachment is not None  # the validator only ever resolves to a real attachment

    job = job_store.create_job(
        sender_email,
        backend_user_id,
        source_message_id,
        operation="submit_transcript",
        group_hint=validated_cmd.group_hint,
        attachment_filename=validated_cmd.attachment.filename,
        original_subject=original_subject,
        original_body_text=original_body_text,
    )
    job_store.set_status(job.job_id, JobState.VALIDATING)

    stored_path = save_incoming(real_attachment.content, real_attachment.filename, storage.incoming)
    job_store.update(job.job_id, attachment_storage_path=str(stored_path))

    try:
        parsed_vtt = parse_vtt(stored_path)
    except VttParseError as e:
        job_store.set_status(job.job_id, JobState.FAILED, error=str(e))
        _fail_and_move(
            job.job_id, stored_path, storage, str(e), outbox, sender_email, job_store,
            in_reply_to, references,
        )
        return HandlerOutcome("rejected", job.job_id)

    meeting_date, meeting_date_source = _resolve_meeting_date(parsed_vtt, validated_cmd.mentioned_date)

    if meeting_date is None:
        # Teams transcripts usually only record relative timestamps, not a calendar date -
        # guessing from the received time would often be wrong, so ask instead of guessing.
        job_store.update(job.job_id, speakers=parsed_vtt.speakers)
        job_store.set_status(job.job_id, JobState.NEEDS_CLARIFICATION)
        question = (
            "I couldn't find a meeting date in the transcript or your email. What date was "
            "this meeting (e.g. '11 August 2026')?"
        )
        pending_clarifications.put(job.job_id, question, "meeting_date", [])
        subject, body = render_clarification(
            question, job.job_id, job.original_subject, job.original_body_text
        )
        outbox.enqueue(
            to_email=sender_email, subject=subject, body_text=body, job_id=job.job_id,
            in_reply_to=in_reply_to, references=references,
        )
        return HandlerOutcome("needs_clarification", job.job_id)

    job_store.update(
        job.job_id,
        speakers=parsed_vtt.speakers,
        meeting_date=meeting_date.isoformat(),
        meeting_date_source=meeting_date_source,
    )
    job_store.set_status(job.job_id, JobState.QUEUED)

    subject, body = render_ack(
        job.job_id, validated_cmd.attachment.filename, meeting_date.isoformat(), group_name=None
    )
    outbox.enqueue(
        to_email=sender_email, subject=subject, body_text=body, job_id=job.job_id,
        in_reply_to=in_reply_to, references=references,
    )
    return HandlerOutcome("job_created", job.job_id)


def execute(
    job: Job,
    diarisation_client: DiarisationClient,
    job_store: JobStore,
    outbox: Outbox,
    admin_notifier: AdminNotifier,
    storage: StorageSettings,
    pending_clarifications: Optional[PendingClarificationStore] = None,
) -> None:
    pending_clarifications = pending_clarifications or PendingClarificationStore(job_store._db_path)
    parent_message_id = job.in_reply_to_message_id or job.source_message_id
    parent_references = parent_message_id
    job_store.set_status(job.job_id, JobState.PROCESSING)
    if job.attachment_storage_path:
        moved = move_to(Path(job.attachment_storage_path), storage.processing)
        job_store.update(job.job_id, attachment_storage_path=str(moved))
        job = job_store.get(job.job_id)  # refresh with the new path

    try:
        graph = build_submit_transcript_graph(diarisation_client)
        result = graph.invoke(
            {
                "job_id": job.job_id,
                "sender_email": job.sender_email,
                "attachment_path": job.attachment_storage_path,
                "attachment_filename": job.attachment_filename,
                "attachment_size_bytes": Path(job.attachment_storage_path).stat().st_size,
                "group_hint": job.group_hint,
                "meeting_date": job.meeting_date,
                "meeting_date_source": job.meeting_date_source,
                "speakers": job.speakers,
            }
        )
        logger.info(
            "Job %s submit graph steps: %s", job.job_id,
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
                to_email=job.sender_email, subject=subject, body_text=body, job_id=job.job_id,
                in_reply_to=parent_message_id, references=parent_references,
            )
            return

        job_store.update(
            job.job_id,
            resolved_group_id=result["group_id"],
            resolved_group_name=result["group_name"],
            backend_meeting_id=result["meeting_id"],
            backend_raw_file_id=result["raw_file_id"],
            resolved_attendees=result.get("resolved_attendees", []),
            unresolved_speakers=result.get("unresolved_speakers", []),
        )
        job_store.set_status(job.job_id, JobState.COMPLETED)

        if job.attachment_storage_path:
            moved = move_to(Path(job.attachment_storage_path), storage.completed)
            job_store.update(job.job_id, attachment_storage_path=str(moved))

        subject, body = render_completion(
            job.job_id,
            result["group_name"],
            job.meeting_date,
            result.get("resolved_attendees", []),
            result.get("unresolved_speakers", []),
        )
        outbox.enqueue(
            to_email=job.sender_email, subject=subject, body_text=body, job_id=job.job_id,
            in_reply_to=parent_message_id, references=parent_references,
        )

    except DiarisationApiError as e:
        logger.exception("Backend API error executing job %s", job.job_id)
        _handle_execute_failure(job, str(e), job_store, outbox, admin_notifier, storage)
    except Exception as e:  # unexpected - still must not crash the worker loop
        logger.exception("Unexpected error executing job %s", job.job_id)
        _handle_execute_failure(job, f"Unexpected error: {e}", job_store, outbox, admin_notifier, storage)


def _handle_execute_failure(
    job: Job,
    reason: str,
    job_store: JobStore,
    outbox: Outbox,
    admin_notifier: AdminNotifier,
    storage: StorageSettings,
) -> None:
    parent_message_id = job.in_reply_to_message_id or job.source_message_id
    parent_references = parent_message_id
    job_store.set_status(job.job_id, JobState.FAILED, error=reason)
    if job.attachment_storage_path and Path(job.attachment_storage_path).exists():
        moved = move_to(Path(job.attachment_storage_path), storage.failed)
        job_store.update(job.job_id, attachment_storage_path=str(moved))

    subject, body = render_failure(
        "We could not reach the backend system to finish processing your transcript. "
        "Please try again later, or contact the admin if this continues.",
        job_id=job.job_id,
    )
    outbox.enqueue(
        to_email=job.sender_email, subject=subject, body_text=body, job_id=job.job_id,
        in_reply_to=parent_message_id, references=parent_references,
    )
    admin_notifier.alert(
        AdminCategory.BACKEND_SUBMISSION_FAILURE,
        f"Job {job.job_id} failed while submitting to the backend.",
        detail={"job_id": job.job_id, "sender": job.sender_email, "reason": reason},
    )


def _fail_and_move(
    job_id: str,
    stored_path: Path,
    storage: StorageSettings,
    reason: str,
    outbox: Outbox,
    sender_email: str,
    job_store: JobStore,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> None:
    if stored_path.exists():
        moved = move_to(stored_path, storage.failed)
        job_store.update(job_id, attachment_storage_path=str(moved))
    subject, body = render_failure(
        f"The attached file could not be read as a valid .vtt transcript: {reason}",
        job_id=job_id,
    )
    outbox.enqueue(
        to_email=sender_email, subject=subject, body_text=body, job_id=job_id,
        in_reply_to=in_reply_to, references=references,
    )


def _resolve_meeting_date(
    parsed_vtt: ParsedVtt, mentioned_date: Optional[str]
) -> tuple[Optional[datetime], Optional[str]]:
    if parsed_vtt.meeting_date is not None:
        return parsed_vtt.meeting_date, "vtt_note"
    if mentioned_date:
        try:
            return dateutil_parser.parse(mentioned_date, fuzzy=True), "email_text"
        except (ValueError, OverflowError, dateutil_parser.ParserError):
            pass
    return None, None
