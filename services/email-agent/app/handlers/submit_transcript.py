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
from app.diarisation.group_matching import Matched, group_clarification_question, match_group
from app.email_templates.render import render_ack, render_clarification, render_completion, render_failure
from app.handlers.base import HandlerOutcome
from app.jobs.models import Job, JobState
from app.jobs.store import JobStore, Outbox, PendingClarificationStore
from app.mail.base import Attachment
from app.settings import StorageSettings
from app.storage.attachments import move_to, save_incoming
from app.vtt.parser import ParsedVtt, VttParseError, parse_vtt

logger = logging.getLogger(__name__)


def accept(
    email_attachments: list[Attachment],
    validated_cmd: ValidatedCommand,
    sender_email: str,
    backend_user_id: int,
    source_message_id: str,
    received_at: datetime,
    job_store: JobStore,
    outbox: Outbox,
    storage: StorageSettings,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> HandlerOutcome:
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

    meeting_date, meeting_date_source = _resolve_meeting_date(
        parsed_vtt, validated_cmd.mentioned_date, received_at
    )

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
        token = diarisation_client.login_for_email(job.sender_email)
        groups = diarisation_client.list_groups(token)

        match = match_group(job.group_hint, groups)
        if not isinstance(match, Matched):
            question = group_clarification_question(match, groups, "this transcript")
            job_store.set_status(job.job_id, JobState.NEEDS_CLARIFICATION)
            pending_clarifications.put(job.job_id, question, "group_hint", [g.name for g in groups])
            subject, body = render_clarification(question, job.job_id)
            outbox.enqueue(
                to_email=job.sender_email, subject=subject, body_text=body, job_id=job.job_id,
                in_reply_to=parent_message_id, references=parent_references,
            )
            return

        group = match.group
        meeting_date = datetime.fromisoformat(job.meeting_date)
        meeting = diarisation_client.create_meeting(
            token, group.id, meeting_date, idempotency_key=job.job_id
        )

        content = Path(job.attachment_storage_path).read_bytes()
        raw_file = diarisation_client.upload_file(
            token, group.id, meeting.id, job.attachment_filename, content
        )

        resolved_attendees: list[str] = []
        unresolved_speakers: list[str] = []
        if job.speakers:
            resolved = diarisation_client.resolve_aliases(token, group.id, job.speakers)
            for name, member_id in resolved.items():
                if member_id is not None:
                    diarisation_client.add_attendee(token, group.id, meeting.id, member_id)
                    resolved_attendees.append(name)
                else:
                    unresolved_speakers.append(name)

        job_store.update(
            job.job_id,
            resolved_group_id=group.id,
            resolved_group_name=group.name,
            backend_meeting_id=meeting.id,
            backend_raw_file_id=raw_file.id,
            resolved_attendees=resolved_attendees,
            unresolved_speakers=unresolved_speakers,
        )
        job_store.set_status(job.job_id, JobState.COMPLETED)

        if job.attachment_storage_path:
            moved = move_to(Path(job.attachment_storage_path), storage.completed)
            job_store.update(job.job_id, attachment_storage_path=str(moved))

        subject, body = render_completion(
            job.job_id, group.name, job.meeting_date, resolved_attendees, unresolved_speakers
        )
        outbox.enqueue(
            to_email=job.sender_email, subject=subject, body_text=body, job_id=job.job_id,
            in_reply_to=parent_message_id, references=parent_references,
        )

    except DiarisationApiError as e:
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
    parsed_vtt: ParsedVtt, mentioned_date: Optional[str], received_at: datetime
) -> tuple[datetime, str]:
    if parsed_vtt.meeting_date is not None:
        return parsed_vtt.meeting_date, "vtt_note"
    if mentioned_date:
        try:
            return dateutil_parser.parse(mentioned_date, fuzzy=True), "email_text"
        except (ValueError, OverflowError, dateutil_parser.ParserError):
            pass
    return received_at, "received_timestamp"
