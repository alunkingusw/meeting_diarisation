from __future__ import annotations

from app.diarisation.client import DiarisationClient
from app.jobs.store import Outbox
from app.mail.base import EmailMessage


class WeeklyReportReplyService:
    """Passes an authenticated report follow-up to the backend and queues its answer."""

    def __init__(self, outbox: Outbox, diarisation: DiarisationClient):
        self._outbox = outbox
        self._diarisation = diarisation

    def reply(self, msg: EmailMessage, report_id: str, sender_email: str) -> None:
        answer = self._diarisation.answer_scheduled_report(
            report_id, sender_email, msg.body_text
        ).strip()
        references = " ".join(dict.fromkeys(
            value for value in (msg.references, msg.in_reply_to, msg.message_id) if value
        ))
        self._outbox.enqueue(
            to_email=sender_email,
            subject=f"Re: Weekly project update - {report_id}",
            body_text=answer,
            job_id=report_id,
            in_reply_to=msg.message_id,
            references=references,
        )
