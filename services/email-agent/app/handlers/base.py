"""Shared handler contract.

Every handler either returns a HandlerOutcome (having already enqueued its own reply to the
Outbox) or raises ClarificationRequired/Rejected - the same exception types used by
commands/validator.py's trust boundary. Both the sync pipeline (status/results/cancel/help) and
the async job worker (submit_transcript.execute) funnel through these same types, so both are
rendered identically by the caller. This is the "be conservative" pattern given a name: real
ambiguity always raises ClarificationRequired rather than guessing.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional

# Re-exported so handlers only need to import from here, not reach into commands.validator.
from app.commands.validator import ClarificationRequired, Rejected
from app.diarisation.client import DiarisationApiError
from app.jobs.models import Job, JobState

__all__ = ["ClarificationRequired", "Rejected", "HandlerOutcome", "STATUS_TEXT", "backend_progress"]

OutcomeType = Literal[
    "job_created",
    "clarification",
    "status_reply",
    "results_reply",
    "cancelled",
    "cannot_cancel",
    "assess_query_reply",
    "help_reply",
    "rejected",
]


@dataclass
class HandlerOutcome:
    outcome_type: OutcomeType
    job_id: Optional[str] = None


STATUS_TEXT: dict[JobState, str] = {
    JobState.RECEIVED: "Received, awaiting validation",
    JobState.VALIDATING: "Being validated",
    JobState.NEEDS_CLARIFICATION: "Waiting on clarification from you",
    JobState.QUEUED: "Queued for processing",
    JobState.PROCESSING: "Currently being processed",
    JobState.COMPLETED: "Completed",
    JobState.FAILED: "Failed",
    JobState.CANCELLED: "Cancelled",
}


_BACKEND_JOB_LABELS = {
    "transcript_processing": "Transcript indexing and summarising",
    "query": "Answer generation",
}


def backend_progress(client, sender_email: str, job: Job) -> Optional[str]:
    """One line on the backend job behind this request, or None. Best effort: a backend that
    can't be reached just means no extra detail."""
    if client is None:
        return None
    try:
        token = client.login_for_email(sender_email)
        if job.backend_job_id:
            backend_job = client.get_job(token, job.backend_job_id)
        elif job.operation == "submit_transcript" and job.backend_meeting_id:
            found = client.list_jobs(
                token, kind="transcript_processing", meeting_id=job.backend_meeting_id
            )
            backend_job = found[0] if found else None
        else:
            return None
    except DiarisationApiError:
        return None
    if backend_job is None:
        return None
    detail = f"{_BACKEND_JOB_LABELS.get(backend_job.kind, backend_job.kind)}: {backend_job.state}"
    if backend_job.progress and not backend_job.finished:
        detail += f" ({backend_job.progress})"
    if backend_job.state == "failed" and backend_job.error:
        detail += f" - {backend_job.error}"
    return detail
