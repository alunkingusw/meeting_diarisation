from __future__ import annotations

from datetime import date

from app.diarisation.client import DiarisationClient
from app.jobs.store import Outbox
from app.mail.base import EmailMessage
from app.reports.store import ReportStore


class WeeklyReportReplyService:
    """Answers follow-up questions about a weekly update from its persisted evidence; the backend
    does the answering."""

    def __init__(self, reports: ReportStore, outbox: Outbox, diarisation: DiarisationClient):
        self._reports = reports
        self._outbox = outbox
        self._diarisation = diarisation

    def reply(self, msg: EmailMessage, report_id: str) -> None:
        report = self._reports.get(report_id)
        if report is None:
            raise ValueError(f"Unknown report {report_id}")
        token = self._diarisation.login_for_email(report.owner_email)
        answer = self._diarisation.answer_report_question(
            token,
            report.group_id,
            msg.body_text,
            self._reports.evidence(report_id),
            date.fromisoformat(report.period_start),
            date.fromisoformat(report.period_end),
        ).strip()
        references = " ".join(dict.fromkeys(
            value for value in (msg.references, msg.in_reply_to, msg.message_id) if value
        ))
        self._outbox.enqueue(
            to_email=msg.from_address,
            subject=f"Re: Weekly project update - {report.report_id}",
            body_text=answer,
            job_id=report.report_id,
            in_reply_to=msg.message_id,
            references=references,
        )
