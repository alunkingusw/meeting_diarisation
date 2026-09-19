"""Persistent job tracking, inbound-message dedup, and the outbound mail queue.

All three stores use short-lived SQLite connections (see storage/db.py) since the mail
pipeline and the job worker run in separate threads and write concurrently.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.jobs.models import ALLOWED_TRANSITIONS, Job, JobState, utcnow_iso
from app.storage.db import get_connection

_JSON_FIELDS = {"speakers", "resolved_attendees", "unresolved_speakers"}
_JSON_COLUMN_NAMES = {
    "speakers": "speakers_json",
    "resolved_attendees": "resolved_attendees_json",
    "unresolved_speakers": "unresolved_speakers_json",
}

# Messages stuck 'in_progress' (e.g. the process crashed mid-handling) are retried up to
# this many times before being given up on and flagged to the admin.
MAX_PROCESSING_ATTEMPTS = 3


class InvalidTransition(Exception):
    """Raised when code attempts to move a job to a status not reachable from its current
    status - a bug-catching guard, not something callers should normally need to handle."""


class JobIdAllocationError(Exception):
    """Raised if a unique job id could not be allocated after repeated collisions."""


class JobStore:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self._db_path)

    def create_job(
        self,
        sender_email: str,
        backend_user_id: int,
        source_message_id: str,
        operation: str = "submit_transcript",
        **initial_fields,
    ) -> Job:
        """Allocate a DIAR-YYYY-MMDD-NNNN job id and insert a RECEIVED job row.

        The counter is per-UTC-day and computed inside the same write transaction as the
        insert; a UNIQUE constraint on job_id is the collision safety net in case two
        threads race for the same number, with a bounded retry on conflict.
        """
        now = datetime.now(timezone.utc)
        prefix = f"DIAR-{now.strftime('%Y')}-{now.strftime('%m%d')}-"

        conn = self._conn()
        try:
            for attempt in range(10):
                conn.execute("BEGIN IMMEDIATE")
                try:
                    row = conn.execute(
                        "SELECT COUNT(*) AS n FROM jobs WHERE job_id LIKE ?",
                        (prefix + "%",),
                    ).fetchone()
                    seq = row["n"] + 1 + attempt
                    job_id = f"{prefix}{seq:04d}"

                    now = utcnow_iso()
                    fields = {
                        "job_id": job_id,
                        "sender_email": sender_email,
                        "backend_user_id": backend_user_id,
                        "source_message_id": source_message_id,
                        "operation": operation,
                        "status": JobState.RECEIVED.value,
                        "created_at": now,
                        **_encode_job_fields(initial_fields),
                    }
                    columns = ", ".join(fields.keys())
                    placeholders = ", ".join("?" for _ in fields)
                    conn.execute(
                        f"INSERT INTO jobs ({columns}) VALUES ({placeholders})",
                        list(fields.values()),
                    )
                    conn.execute("COMMIT")
                    return self.get(job_id)  # type: ignore[return-value]
                except sqlite3.IntegrityError:
                    conn.execute("ROLLBACK")
                    continue
            raise JobIdAllocationError(
                f"Could not allocate a unique job id with prefix {prefix} after 10 attempts"
            )
        finally:
            conn.close()

    def get(self, job_id: str) -> Optional[Job]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            return Job.from_row(row) if row else None
        finally:
            conn.close()

    def get_owned(self, job_id: str, sender_email: str) -> Optional[Job]:
        """Look up a job only if it belongs to sender_email - never reveals whether a job_id
        exists at all to a sender who doesn't own it."""
        job = self.get(job_id)
        if job is None or job.sender_email.lower() != sender_email.lower():
            return None
        return job

    def update(self, job_id: str, **fields) -> None:
        if not fields:
            return
        encoded = _encode_job_fields(fields)
        assignments = ", ".join(f"{k} = ?" for k in encoded)
        conn = self._conn()
        try:
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE job_id = ?",
                [*encoded.values(), job_id],
            )
        finally:
            conn.close()

    def set_status(self, job_id: str, new_status: JobState, **extra) -> None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT status FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise InvalidTransition(f"Job {job_id} does not exist")
            current = JobState(row["status"])
            if new_status not in ALLOWED_TRANSITIONS.get(current, set()) and new_status != current:
                raise InvalidTransition(f"Cannot move job {job_id} from {current} to {new_status}")

            fields = {"status": new_status.value, **_encode_job_fields(extra)}
            if new_status == JobState.PROCESSING and "started_at" not in fields:
                fields["started_at"] = utcnow_iso()
            if new_status in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED) and (
                "completed_at" not in fields
            ):
                fields["completed_at"] = utcnow_iso()

            assignments = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE job_id = ?",
                [*fields.values(), job_id],
            )
        finally:
            conn.close()

    def get_by_last_response_message_id(self, message_id: str, sender_email: str) -> Optional[Job]:
        """Used by ThreadMatcher to associate a reply with the job whose response it's
        replying to. Scoped to sender_email so a forwarded/quoted message-id can't be used to
        act on someone else's job."""
        conn = self._conn()
        try:
            row = conn.execute(
                """SELECT * FROM jobs
                   WHERE last_response_message_id = ? AND sender_email = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (message_id, sender_email),
            ).fetchone()
            return Job.from_row(row) if row else None
        finally:
            conn.close()

    def get_by_response_message_id(self, message_id: str, sender_email: str) -> Optional[Job]:
        """Find a sender-owned job through any outbound response in its thread."""
        conn = self._conn()
        try:
            row = conn.execute(
                """SELECT jobs.* FROM jobs
                   JOIN message_links ON message_links.job_id = jobs.job_id
                   WHERE message_links.message_id = ? AND LOWER(jobs.sender_email) = LOWER(?)
                   ORDER BY message_links.created_at DESC LIMIT 1""",
                (message_id, sender_email),
            ).fetchone()
            return Job.from_row(row) if row else None
        finally:
            conn.close()

    def list_queued(self) -> list[Job]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at ASC",
                (JobState.QUEUED.value,),
            ).fetchall()
            return [Job.from_row(r) for r in rows]
        finally:
            conn.close()


def _encode_job_fields(fields: dict) -> dict:
    encoded = {}
    for k, v in fields.items():
        if k in _JSON_FIELDS:
            encoded[_JSON_COLUMN_NAMES[k]] = json.dumps(v)
        elif k in _JSON_COLUMN_NAMES.values():
            encoded[k] = v if isinstance(v, str) else json.dumps(v)
        elif isinstance(v, JobState):
            encoded[k] = v.value
        else:
            encoded[k] = v
    return encoded


class ProcessedMessageStore:
    """Dedup + crash-recovery lock for inbound messages, keyed on Message-ID.

    The UNIQUE(message_id) primary key is the actual dedup mechanism: begin() attempts an
    INSERT and treats a collision as "already seen" unless that prior attempt is still
    'in_progress' and hasn't exhausted its retry budget (i.e. the process likely crashed
    mid-handling last time).
    """

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self._db_path)

    def begin(self, message_id: str, sender_email: str, auth_result: str) -> bool:
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """INSERT INTO processed_messages
                       (message_id, received_at, sender_email, auth_result, outcome, attempt_count)
                       VALUES (?, ?, ?, ?, 'in_progress', 1)""",
                    (message_id, utcnow_iso(), sender_email, auth_result),
                )
                conn.execute("COMMIT")
                return True
            except sqlite3.IntegrityError:
                conn.execute("ROLLBACK")

            row = conn.execute(
                "SELECT outcome, attempt_count FROM processed_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            if row is None:
                return False
            if row["outcome"] == "in_progress" and row["attempt_count"] < MAX_PROCESSING_ATTEMPTS:
                conn.execute(
                    "UPDATE processed_messages SET attempt_count = attempt_count + 1 WHERE message_id = ?",
                    (message_id,),
                )
                return True
            return False
        finally:
            conn.close()

    def finalize(
        self,
        message_id: str,
        outcome: str,
        job_id: Optional[str] = None,
        operation: Optional[str] = None,
    ) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE processed_messages
                   SET outcome = ?, job_id = ?, operation = ?, processed_at = ?
                   WHERE message_id = ?""",
                (outcome, job_id, operation, utcnow_iso(), message_id),
            )
        finally:
            conn.close()

    def get_outcome(self, message_id: str) -> Optional[str]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT outcome FROM processed_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            return row["outcome"] if row else None
        finally:
            conn.close()


@dataclass
class OutboxMessage:
    id: int
    job_id: Optional[str]
    to_email: str
    subject: str
    body_text: str
    attachments: list[str] = field(default_factory=list)
    in_reply_to_message_id: Optional[str] = None
    references_header: Optional[str] = None
    status: str = "PENDING"
    attempts: int = 0
    last_error: Optional[str] = None

    @property
    def references(self) -> Optional[str]:
        """Compatibility alias for callers inspecting the RFC References header."""
        return self.references_header

    @classmethod
    def from_row(cls, row) -> "OutboxMessage":
        return cls(
            id=row["id"],
            job_id=row["job_id"],
            to_email=row["to_email"],
            subject=row["subject"],
            body_text=row["body_text"],
            attachments=json.loads(row["attachments_json"]) if row["attachments_json"] else [],
            in_reply_to_message_id=row["in_reply_to_message_id"],
            references_header=row["references_header"],
            status=row["status"],
            attempts=row["attempts"],
            last_error=row["last_error"],
        )


class Outbox:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self._db_path)

    def enqueue(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        job_id: Optional[str] = None,
        attachments: Optional[list[str]] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                """INSERT INTO outbox
                   (job_id, to_email, subject, body_text, attachments_json,
                    in_reply_to_message_id, references_header, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
                (
                    job_id,
                    to_email,
                    subject,
                    body_text,
                    json.dumps(attachments or []),
                    in_reply_to,
                    references,
                    utcnow_iso(),
                ),
            )
            return cur.lastrowid
        finally:
            conn.close()

    def pending(self) -> list[OutboxMessage]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM outbox WHERE status = 'PENDING' ORDER BY created_at ASC"
            ).fetchall()
            return [OutboxMessage.from_row(r) for r in rows]
        finally:
            conn.close()

    def mark_sent(self, outbox_id: int, provider_message_id: Optional[str] = None) -> None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT job_id FROM outbox WHERE id = ?", (outbox_id,)
            ).fetchone()
            conn.execute(
                "UPDATE outbox SET status = 'SENT', sent_at = ? WHERE id = ?",
                (utcnow_iso(), outbox_id),
            )
            if provider_message_id:
                conn.execute(
                    """INSERT INTO message_links
                       (outbox_id, job_id, message_id, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (outbox_id, row["job_id"] if row else None, provider_message_id, utcnow_iso()),
                )
        finally:
            conn.close()

    def mark_failed(self, outbox_id: int, error: str, max_attempts: int = 5) -> None:
        """Record a failed send attempt. Per spec S20 ("email sending fails"), the message
        stays PENDING and is retried on the next flush cycle until max_attempts is reached,
        at which point it's given up on (status FAILED) rather than retried forever."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT attempts FROM outbox WHERE id = ?", (outbox_id,)
            ).fetchone()
            attempts = (row["attempts"] if row else 0) + 1
            status = "FAILED" if attempts >= max_attempts else "PENDING"
            conn.execute(
                "UPDATE outbox SET status = ?, attempts = ?, last_error = ? WHERE id = ?",
                (status, attempts, error, outbox_id),
            )
        finally:
            conn.close()


@dataclass
class PendingClarification:
    job_id: str
    question: str
    expected_field: str
    options: list[str] = field(default_factory=list)
    created_at: str = ""


class PendingClarificationStore:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self._db_path)

    def put(self, job_id: str, question: str, expected_field: str, options: list[str]) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO pending_clarifications
                   (job_id, question, expected_field, options_json, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(job_id) DO UPDATE SET
                     question = excluded.question,
                     expected_field = excluded.expected_field,
                     options_json = excluded.options_json,
                     created_at = excluded.created_at""",
                (job_id, question, expected_field, json.dumps(options), utcnow_iso()),
            )
        finally:
            conn.close()

    def get(self, job_id: str) -> Optional[PendingClarification]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM pending_clarifications WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return None
            return PendingClarification(
                job_id=row["job_id"],
                question=row["question"],
                expected_field=row["expected_field"],
                options=json.loads(row["options_json"]),
                created_at=row["created_at"],
            )
        finally:
            conn.close()

    def delete(self, job_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM pending_clarifications WHERE job_id = ?", (job_id,))
        finally:
            conn.close()
