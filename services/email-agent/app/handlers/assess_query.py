"""Answers an email query through the backend's unified parent-query API.

The validated command's per-source focuses are passed to one parent request after the sender
and group have been resolved. Split into accept() (local-only: create the job, done inline in
the mail-polling pipeline) and execute() (backend API call, run by the job worker thread),
mirroring submit_transcript.py's split so a slow/unavailable source never blocks mail polling.

A source being unreachable degrades the reply (a note saying so) rather than failing the whole
job, as long as at least one requested source answered - matching the "still send something
useful on partial failure" pattern from ROADMAP.md's weekly-update design notes.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import uuid4

from app.admin.notifier import AdminCategory, AdminNotifier
from app.commands.validator import ValidatedCommand
from app.diarisation.client import DiarisationApiError, DiarisationClient, JobCancelledError, NotFoundError
from app.diarisation.group_matching import Matched, group_clarification_question, match_group
from app.email_templates.render import (
    render_assess_ack,
    render_assess_result,
    render_clarification,
    render_failure,
)
from app.handlers.base import HandlerOutcome
from app.jobs.models import Job, JobState
from app.jobs.store import JobStore, Outbox, PendingClarificationStore

logger = logging.getLogger(__name__)

_SOURCE_LABELS = {
    "conversation": "past meeting transcripts",
    "github": "the GitHub repo",
    "trello": "the Trello board",
}


def _source_unavailable_note(source: str, detail: str) -> str:
    message = detail.lower()
    if source == "github" and "no github source linked" in message:
        return "Your group doesn't have a GitHub repo linked yet, so I couldn't check it."
    if source == "trello" and "no trello source linked" in message:
        return "Your group doesn't have a Trello board linked yet, so I couldn't check it."
    return f"I couldn't check {_SOURCE_LABELS[source]} right now."


def _was_cancelled(job: Job, job_store: JobStore) -> bool:
    current = job_store.get(job.job_id)
    return current is not None and current.status == JobState.CANCELLED


def _mark_cancelled(job: Job, job_store: JobStore) -> None:
    """The backend job was cancelled; the cancel email (or the API) already told the user."""
    if not _was_cancelled(job, job_store):
        job_store.set_status(job.job_id, JobState.CANCELLED)


def _query_evidence_refs(results: dict[str, dict]) -> list[dict[str, str]]:
    references = []
    for source, result in results.items():
        if source not in _SOURCE_LABELS or not isinstance(result, dict):
            continue
        for evidence in result.get("evidence", []):
            evidence_id = evidence.get("id") if isinstance(evidence, dict) else None
            if evidence_id:
                references.append({"source": source, "id": str(evidence_id)})
    return references


def accept(
    validated_cmd: ValidatedCommand,
    sender_email: str,
    backend_user_id: int,
    source_message_id: str,
    job_store: JobStore,
    outbox: Outbox,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    original_subject: Optional[str] = None,
    original_body_text: Optional[str] = None,
    thread_job_id: Optional[str] = None,
) -> HandlerOutcome:
    parent_job = (
        job_store.get_owned(thread_job_id, sender_email) if thread_job_id else None
    )
    if (
        parent_job is not None
        and parent_job.operation == "assess_query"
        and parent_job.status == JobState.COMPLETED
        and parent_job.resolved_group_id is not None
        and backend_user_id is not None
        and parent_job.backend_user_id == backend_user_id
    ):
        conversation_id = parent_job.query_conversation_id or str(uuid4())
        parent_query_job_id = parent_job.job_id
    else:
        conversation_id = str(uuid4())
        parent_query_job_id = None

    job = job_store.create_job(
        sender_email,
        backend_user_id,
        source_message_id,
        operation="assess_query",
        group_hint=validated_cmd.group_hint,
        transcript_focus=validated_cmd.transcript_focus,
        github_focus=validated_cmd.github_focus,
        trello_focus=validated_cmd.trello_focus,
        original_subject=original_subject,
        original_body_text=original_body_text,
        query_conversation_id=conversation_id,
        query_parent_job_id=parent_query_job_id,
    )
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)

    subject, body = render_assess_ack(job.job_id)
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
    pending_clarifications: Optional[PendingClarificationStore] = None,
) -> None:
    pending_clarifications = pending_clarifications or PendingClarificationStore(job_store._db_path)
    parent_message_id = job.in_reply_to_message_id or job.source_message_id
    parent_references = parent_message_id
    job_store.set_status(job.job_id, JobState.PROCESSING)

    try:
        token = diarisation_client.login_for_email(job.sender_email)
        groups = diarisation_client.list_groups(token)

        match = match_group(job.group_hint, groups)
        if not isinstance(match, Matched):
            question = group_clarification_question(match, groups, "this question")
            job_store.set_status(job.job_id, JobState.NEEDS_CLARIFICATION)
            pending_clarifications.put(job.job_id, question, "group_hint", [g.name for g in groups])
            subject, body = render_clarification(
                question, job.job_id, job.original_subject, job.original_body_text
            )
            outbox.enqueue(
                to_email=job.sender_email, subject=subject, body_text=body, job_id=job.job_id,
                in_reply_to=parent_message_id, references=parent_references,
            )
            return

        group = match.group
        job_store.update(
            job.job_id,
            resolved_group_id=group.id,
            resolved_group_name=group.name,
        )
        if job.query_parent_job_id:
            parent_job = job_store.get_owned(job.query_parent_job_id, job.sender_email)
            if (
                parent_job is None
                or parent_job.operation != "assess_query"
                or parent_job.backend_user_id != job.backend_user_id
                or (
                    parent_job.resolved_group_id is not None
                    and parent_job.resolved_group_id != group.id
                )
            ):
                job_store.update(job.job_id, query_conversation_id=str(uuid4()))

        track = lambda backend_job_id: job_store.update(job.job_id, backend_job_id=backend_job_id)  # noqa: E731
        source_questions = {
            name: focus
            for name, focus in (
                ("conversation", job.transcript_focus),
                ("github", job.github_focus),
                ("trello", job.trello_focus),
            )
            if focus
        }
        sources = list(source_questions)
        unified_answer: Optional[str] = None
        unavailable_notes: list[str] = []
        query_result = None

        if _was_cancelled(job, job_store):
            return
        if sources:
            try:
                query_result = diarisation_client.query_unified(
                    token,
                    group.id,
                    "Answer the sender's request using the source-specific questions provided.",
                    sources=sources,
                    source_questions=source_questions,
                    on_job=track,
                )
                unified_answer = query_result.answer
                unavailable_notes.extend(
                    _source_unavailable_note(name, detail)
                    for name, detail in query_result.errors.items()
                    if name in _SOURCE_LABELS
                )
            except JobCancelledError:
                _mark_cancelled(job, job_store)
                return
            except NotFoundError as exc:
                if sources == ["conversation"]:
                    unified_answer = "I didn't find anything in past meeting transcripts that speaks to this."
                else:
                    unavailable_notes.extend(
                        _source_unavailable_note(source, str(exc)) for source in sources
                    )
            except DiarisationApiError:
                logger.exception("Unified parent query failed for job %s", job.job_id)
                unavailable_notes.extend(
                    _source_unavailable_note(source, "backend query failed") for source in sources
                )

        if _was_cancelled(job, job_store):
            return
        if unified_answer is None:
            reason = "None of the sources I needed to answer this were reachable just now."
            if unavailable_notes:
                reason += " " + " ".join(unavailable_notes)
            _handle_failure(job, reason, job_store, outbox, admin_notifier)
            return

        job_store.record_query_turn(
            job.job_id,
            selected_sources=sources,
            evidence_refs=_query_evidence_refs(query_result.results) if query_result else [],
            failed_sources=list(query_result.errors) if query_result else [],
            model=query_result.model if query_result else None,
        )
        job_store.set_status(job.job_id, JobState.COMPLETED)
        subject, body = render_assess_result(
            job.job_id,
            group.name,
            None,
            None,
            trello_checked=False,
            unavailable_notes=unavailable_notes,
            unified_answer=unified_answer,
        )
        outbox.enqueue(
            to_email=job.sender_email, subject=subject, body_text=body, job_id=job.job_id,
            in_reply_to=parent_message_id, references=parent_references,
        )

    except DiarisationApiError as e:
        logger.exception("Backend API error executing job %s", job.job_id)
        _handle_failure(job, f"Could not reach the backend to resolve your group: {e}", job_store, outbox, admin_notifier)
    except Exception as e:  # unexpected - still must not crash the worker loop or leave the job stuck
        logger.exception("Unexpected error executing job %s", job.job_id)
        _handle_failure(job, f"Unexpected error: {e}", job_store, outbox, admin_notifier)


def _handle_failure(
    job: Job, reason: str, job_store: JobStore, outbox: Outbox, admin_notifier: AdminNotifier
) -> None:
    parent_message_id = job.in_reply_to_message_id or job.source_message_id
    parent_references = parent_message_id
    job_store.set_status(job.job_id, JobState.FAILED, error=reason)
    subject, body = render_failure(reason, job_id=job.job_id)
    outbox.enqueue(
        to_email=job.sender_email, subject=subject, body_text=body, job_id=job.job_id,
        in_reply_to=parent_message_id, references=parent_references,
    )
    admin_notifier.alert(
        AdminCategory.ASSESS_QUERY_FAILURE,
        f"Job {job.job_id} failed while answering an assess_query.",
        detail={"job_id": job.job_id, "sender": job.sender_email, "reason": reason},
    )
