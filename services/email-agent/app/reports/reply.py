from __future__ import annotations

from app.jobs.store import Outbox
from app.llm.ollama_client import OllamaClient
from app.mail.base import EmailMessage
from app.reports.store import ReportStore

REPLY_SYSTEM_PROMPT = """Answer the user's question using only the weekly report evidence supplied.
Do not invent facts. Cite factual claims with the supplied evidence citation. If the evidence
does not answer the question, say so and explain which source would need a fresh lookup. You may
explain meetings, GitHub, and Trello evidence together, but keep source boundaries clear."""


class WeeklyReportReplyService:
    def __init__(self, reports: ReportStore, outbox: Outbox, ollama: OllamaClient):
        self._reports = reports
        self._outbox = outbox
        self._ollama = ollama

    def reply(self, msg: EmailMessage, report_id: str) -> None:
        report = self._reports.get(report_id)
        if report is None:
            raise ValueError(f"Unknown report {report_id}")
        evidence = self._reports.evidence(report_id)
        evidence_text = "\n\n".join(
            f"Source: {item.source}\nCitation: [{item.citation}]\n{item.content}"
            for item in evidence
        )
        prompt = (
            f"Project: {report.group_name}\n"
            f"Reporting period: {report.period_start} to {report.period_end}\n"
            f"User question: {msg.body_text}\n\n"
            f"Persisted evidence:\n{evidence_text or '(No evidence was persisted.)'}"
        )
        answer = self._ollama.generate(REPLY_SYSTEM_PROMPT, prompt, json_mode=False).strip()
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
