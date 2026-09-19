"""Deterministic association of an inbound reply with an existing job.

Never LLM-inferred (spec S16) - only header-based (In-Reply-To/References against any recorded
outbound response) or a single unambiguous DIAR-YYYY-MMDD-NNNN reference in the subject/body,
and only ever resolved against jobs owned by the sender.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.jobs.store import JobStore
    from app.mail.base import EmailMessage

JOB_ID_RE = re.compile(r"DIAR-\d{4}-\d{4}-\d{4}")
_MESSAGE_ID_TOKEN_RE = re.compile(r"<[^<>\s]+>")


class ThreadMatcher:
    def __init__(self, job_store: "JobStore"):
        self._job_store = job_store

    def match(self, msg: "EmailMessage", sender_email: str) -> Optional[str]:
        for ref in _referenced_message_ids(msg.in_reply_to, msg.references):
            job = self._job_store.get_by_response_message_id(ref, sender_email)
            if job is None:
                job = self._job_store.get_by_last_response_message_id(ref, sender_email)
            if job:
                return job.job_id

        found = set(JOB_ID_RE.findall(msg.subject or "")) | set(
            JOB_ID_RE.findall(msg.body_text or "")
        )
        if len(found) == 1:
            job = self._job_store.get_owned(next(iter(found)), sender_email)
            if job:
                return job.job_id

        return None


def _referenced_message_ids(in_reply_to: Optional[str], references: Optional[str]) -> list[str]:
    raw = " ".join(filter(None, [in_reply_to, references]))
    tokens = _MESSAGE_ID_TOKEN_RE.findall(raw)
    if tokens:
        return tokens
    # Some providers surface the id without angle brackets - fall back to the raw value.
    return [raw.strip()] if raw.strip() else []
