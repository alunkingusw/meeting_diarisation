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
from app.jobs.models import JobState

__all__ = ["ClarificationRequired", "Rejected", "HandlerOutcome", "STATUS_TEXT"]

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
