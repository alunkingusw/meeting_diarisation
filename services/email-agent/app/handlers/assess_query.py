"""Answers a sender's question by querying real sources - past meeting transcripts
and/or the group's GitHub repo and Trello board, all through the backend's query API - for
whichever of transcript_focus/github_focus/trello_focus the LLM set. Split into accept()
(local-only: create the job, done inline in the mail-polling pipeline) and execute() (all
external HTTP + LLM calls, run by the job worker thread), mirroring submit_transcript.py's
split for the same reason: a slow/unavailable source should never block mail polling.

A source being unreachable degrades the reply (a note saying so) rather than failing the whole
job, as long as at least one requested source answered - matching the "still send something
useful on partial failure" pattern from ROADMAP.md's weekly-update design notes.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.admin.notifier import AdminCategory, AdminNotifier
from app.commands.validator import ValidatedCommand
from app.diarisation.client import DiarisationApiError, DiarisationClient, NotFoundError
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

_SOURCE_LABELS = {"github": "the GitHub repo", "trello": "the Trello board"}


def _project_sources_label(sources: list[str]) -> str:
    return " or ".join({"github": "a GitHub repo", "trello": "a Trello board"}[s] for s in sources)


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
) -> HandlerOutcome:
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
        transcript_answer: Optional[str] = None
        github_trello_answer: Optional[str] = None
        unavailable_notes: list[str] = []

        if job.transcript_focus:
            try:
                transcript_answer = diarisation_client.query_source(
                    token, group.id, "conversation", job.transcript_focus
                ).answer
            except NotFoundError:
                transcript_answer = "I didn't find anything in past transcripts that speaks to this."
            except DiarisationApiError:
                logger.exception("Transcript query failed for job %s", job.job_id)
                unavailable_notes.append("I couldn't check past meeting transcripts right now.")

        project_sources = [
            name for name, focus in (("github", job.github_focus), ("trello", job.trello_focus)) if focus
        ]
        if project_sources:
            question = " ".join(f for f in (job.github_focus, job.trello_focus) if f)
            try:
                if len(project_sources) == 1:
                    result = diarisation_client.query_source(token, group.id, project_sources[0], question)
                else:
                    result = diarisation_client.query_unified(
                        token, group.id, question, sources=project_sources
                    )
                github_trello_answer = result.answer
                unavailable_notes.extend(
                    f"I couldn't check {_SOURCE_LABELS[name]} right now."
                    for name in result.errors
                    if name in _SOURCE_LABELS
                )
            except NotFoundError:
                unavailable_notes.append(
                    f"Your group doesn't have {_project_sources_label(project_sources)} linked yet, "
                    "so I couldn't check it."
                )
            except DiarisationApiError:
                logger.exception("GitHub/Trello query failed for job %s", job.job_id)
                unavailable_notes.append("I couldn't check the GitHub repo/Trello board right now.")

        if transcript_answer is None and github_trello_answer is None:
            reason = "None of the sources I needed to answer this were reachable just now."
            if unavailable_notes:
                reason += " " + " ".join(unavailable_notes)
            _handle_failure(job, reason, job_store, outbox, admin_notifier)
            return

        job_store.set_status(job.job_id, JobState.COMPLETED)
        subject, body = render_assess_result(
            job.job_id,
            group.name,
            transcript_answer,
            github_trello_answer,
            trello_checked=bool(job.trello_focus and github_trello_answer),
            unavailable_notes=unavailable_notes,
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
