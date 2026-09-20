"""Dispatch graph-backed command execution for the manager client.

This is intentionally narrow: it exposes graph execution for the command shapes the email agent
already models, while leaving the deterministic pipeline as the default runtime mechanism until
we validate parity on a real fixture set.
"""
from __future__ import annotations

from app.diarisation.client import DiarisationClient
from app.email_templates.render import (
    render_cancelled,
    render_cannot_cancel,
    render_help,
    render_results,
    render_status,
)
from app.handlers.base import HandlerOutcome, STATUS_TEXT
from app.jobs.models import JobState
from app.llm.comment_graph import build_add_comment_graph


class CommandGraphDispatcher:
    def __init__(self, diarisation_client: DiarisationClient | None = None, outbox=None):
        self._client = diarisation_client
        self._outbox = outbox
        self._store = getattr(diarisation_client, "_job_store", diarisation_client)
        if diarisation_client is not None:
            self._add_comment_graph = build_add_comment_graph(diarisation_client)

    def execute_add_comment(self, sender_email: str, group_id: int, meeting_id: int, comment: str):
        return self._add_comment_graph.invoke(
            {
                "sender_email": sender_email,
                "group_id": group_id,
                "meeting_id": meeting_id,
                "comment": comment,
            }
        )

    def execute_status(
        self,
        job_id: str,
        sender_email: str,
        outbox=None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> HandlerOutcome:
        target_outbox = outbox or self._outbox
        if target_outbox is None:
            raise ValueError("an outbox is required for status execution")
        job = self._store.get_owned(job_id, sender_email)
        status_text = STATUS_TEXT.get(job.status, job.status.value)
        subject, body = render_status(job.job_id, status_text)
        target_outbox.enqueue(
            to_email=sender_email,
            subject=subject,
            body_text=body,
            job_id=job.job_id,
            in_reply_to=in_reply_to,
            references=references,
        )
        return HandlerOutcome("status_reply", job.job_id)

    def execute_results(
        self,
        job_id: str,
        sender_email: str,
        outbox=None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> HandlerOutcome:
        target_outbox = outbox or self._outbox
        if target_outbox is None:
            raise ValueError("an outbox is required for results execution")
        job = self._store.get_owned(job_id, sender_email)
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
        target_outbox.enqueue(
            to_email=sender_email,
            subject=subject,
            body_text=body,
            job_id=job.job_id,
            in_reply_to=in_reply_to,
            references=references,
        )
        return HandlerOutcome("results_reply", job.job_id)

    def execute_help(
        self,
        sender_email: str,
        outbox=None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> HandlerOutcome:
        target_outbox = outbox or self._outbox
        if target_outbox is None:
            raise ValueError("an outbox is required for help execution")
        subject, body = render_help()
        target_outbox.enqueue(
            to_email=sender_email,
            subject=subject,
            body_text=body,
            in_reply_to=in_reply_to,
            references=references,
        )
        return HandlerOutcome("help_reply")

    def execute_cancel(
        self,
        job_id: str,
        sender_email: str,
        outbox=None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> HandlerOutcome:
        target_outbox = outbox or self._outbox
        if target_outbox is None:
            raise ValueError("an outbox is required for cancel execution")
        job = self._store.get_owned(job_id, sender_email)
        if job.status in {JobState.QUEUED, JobState.NEEDS_CLARIFICATION}:
            self._store.set_status(job.job_id, JobState.CANCELLED)
            subject, body = render_cancelled(job.job_id)
            target_outbox.enqueue(
                to_email=sender_email,
                subject=subject,
                body_text=body,
                job_id=job.job_id,
                in_reply_to=in_reply_to,
                references=references,
            )
            return HandlerOutcome("cancelled", job.job_id)

        status_text = STATUS_TEXT.get(job.status, job.status.value)
        subject, body = render_cannot_cancel(job.job_id, status_text)
        target_outbox.enqueue(
            to_email=sender_email,
            subject=subject,
            body_text=body,
            job_id=job.job_id,
            in_reply_to=in_reply_to,
            references=references,
        )
        return HandlerOutcome("cannot_cancel", job.job_id)
