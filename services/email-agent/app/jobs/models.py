from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class JobState(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Valid state transitions. Enforced by JobStore.set_status so an inconsistent job state can
# never be written, regardless of which caller (mail pipeline thread or job worker thread)
# is driving it.
ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.RECEIVED: {JobState.VALIDATING, JobState.FAILED},
    JobState.VALIDATING: {JobState.QUEUED, JobState.NEEDS_CLARIFICATION, JobState.FAILED},
    JobState.NEEDS_CLARIFICATION: {JobState.QUEUED, JobState.CANCELLED, JobState.FAILED},
    JobState.QUEUED: {JobState.PROCESSING, JobState.CANCELLED},
    JobState.PROCESSING: {
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.NEEDS_CLARIFICATION,
    },
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    job_id: str
    sender_email: str
    backend_user_id: int
    source_message_id: str
    status: JobState
    operation: str = "submit_transcript"
    group_hint: Optional[str] = None
    resolved_group_id: Optional[int] = None
    resolved_group_name: Optional[str] = None
    attachment_filename: Optional[str] = None
    attachment_storage_path: Optional[str] = None
    meeting_date: Optional[str] = None
    meeting_date_source: Optional[str] = None
    speakers: list[str] = field(default_factory=list)
    backend_meeting_id: Optional[int] = None
    backend_raw_file_id: Optional[int] = None
    resolved_attendees: list[dict] = field(default_factory=list)
    unresolved_speakers: list[str] = field(default_factory=list)
    transcript_focus: Optional[str] = None
    github_focus: Optional[str] = None
    trello_focus: Optional[str] = None
    comment_text: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    created_at: str = field(default_factory=utcnow_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    last_response_message_id: Optional[str] = None
    in_reply_to_message_id: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "Job":
        return cls(
            job_id=row["job_id"],
            sender_email=row["sender_email"],
            backend_user_id=row["backend_user_id"],
            source_message_id=row["source_message_id"],
            operation=row["operation"],
            status=JobState(row["status"]),
            group_hint=row["group_hint"],
            resolved_group_id=row["resolved_group_id"],
            resolved_group_name=row["resolved_group_name"],
            attachment_filename=row["attachment_filename"],
            attachment_storage_path=row["attachment_storage_path"],
            meeting_date=row["meeting_date"],
            meeting_date_source=row["meeting_date_source"],
            speakers=json.loads(row["speakers_json"]) if row["speakers_json"] else [],
            backend_meeting_id=row["backend_meeting_id"],
            backend_raw_file_id=row["backend_raw_file_id"],
            resolved_attendees=(
                json.loads(row["resolved_attendees_json"])
                if row["resolved_attendees_json"]
                else []
            ),
            unresolved_speakers=(
                json.loads(row["unresolved_speakers_json"])
                if row["unresolved_speakers_json"]
                else []
            ),
            transcript_focus=row["transcript_focus"],
            github_focus=row["github_focus"],
            trello_focus=row["trello_focus"],
            comment_text=row["comment_text"],
            error=row["error"],
            retry_count=row["retry_count"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            last_response_message_id=row["last_response_message_id"],
            in_reply_to_message_id=row["in_reply_to_message_id"],
        )
