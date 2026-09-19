from __future__ import annotations

import logging
from datetime import date
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.admin.notifier import AdminCategory, AdminNotifier
from app.diarisation.client import DiarisationClient, GroupSummary
from app.github_raginator.client import GithubRaginatorClient
from app.jobs.store import Outbox
from app.llm.ollama_client import OllamaClient
from app.reports.models import ReportEvidence
from app.reports.sources import WeeklySourceCollector
from app.reports.store import ReportStore

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = """You write a weekly project update using only the evidence supplied.
Do not invent events, dates, people, status, or causes. Separate the report into Meetings,
GitHub, and Trello. If a source has no evidence, say that no evidence was found. If a source
was unavailable, state that explicitly. Cite every factual statement with the supplied citation
in square brackets. Keep the email concise and plain text."""


class ReportState(TypedDict, total=False):
    report_id: str
    evidence: list[ReportEvidence]
    unavailable: list[str]
    report_text: str
    error: Optional[str]


class WeeklyReportWorkflow:
    """Durable report orchestration expressed as a small, inspectable LangGraph.

    External clients remain deterministic tools owned by application code. The LLM only turns
    persisted source evidence into prose; it never chooses a source or performs an API action.
    """

    def __init__(
        self,
        report_store: ReportStore,
        outbox: Outbox,
        diarisation: DiarisationClient,
        github: GithubRaginatorClient,
        ollama: OllamaClient,
        admin: AdminNotifier,
    ):
        self._reports = report_store
        self._outbox = outbox
        self._sources = WeeklySourceCollector(diarisation, github)
        self._diarisation = diarisation
        self._ollama = ollama
        self._admin = admin
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(ReportState)
        graph.add_node("load", self._load)
        graph.add_node("collect", self._collect)
        graph.add_node("persist", self._persist)
        graph.add_node("synthesise", self._synthesise)
        graph.add_node("enqueue", self._enqueue)
        graph.add_edge(START, "load")
        graph.add_edge("load", "collect")
        graph.add_edge("collect", "persist")
        graph.add_edge("persist", "synthesise")
        graph.add_edge("synthesise", "enqueue")
        graph.add_edge("enqueue", END)
        return graph.compile()

    def run(self, report_id: str) -> None:
        report = self._reports.get(report_id)
        if report is None:
            raise ValueError(f"Unknown weekly report {report_id}")
        if report.status in {"COMPLETED", "QUEUED", "SENT"}:
            return
        try:
            self._graph.invoke({"report_id": report_id})
        except Exception as exc:
            logger.exception("Weekly report %s failed", report_id)
            self._reports.set_status(report_id, "FAILED", error=str(exc))
            self._admin.alert(
                AdminCategory.INFRASTRUCTURE,
                f"Weekly report {report_id} failed: {exc}",
            )

    def _load(self, state: ReportState) -> ReportState:
        report = self._reports.get(state["report_id"])
        if report is None:
            raise ValueError(f"Unknown weekly report {state['report_id']}")
        self._reports.set_status(report.report_id, "COLLECTING")
        return {"report_id": report.report_id, "evidence": [], "unavailable": []}

    def _collect(self, state: ReportState) -> ReportState:
        report = self._reports.get(state["report_id"])
        if report is None:
            raise ValueError(f"Unknown weekly report {state['report_id']}")
        token = self._diarisation.login_for_email(report.owner_email)
        group = GroupSummary(id=report.group_id, name=report.group_name)
        collected = self._sources.collect(
            token,
            group,
            date.fromisoformat(report.period_start),
            date.fromisoformat(report.period_end),
        )
        return {"evidence": collected.evidence, "unavailable": collected.unavailable}

    def _persist(self, state: ReportState) -> ReportState:
        report_id = state["report_id"]
        self._reports.replace_evidence(report_id, state.get("evidence", []))
        self._reports.set_status(report_id, "SYNTHESISING")
        return state

    def _synthesise(self, state: ReportState) -> ReportState:
        report = self._reports.get(state["report_id"])
        if report is None:
            raise ValueError(f"Unknown weekly report {state['report_id']}")
        evidence = state.get("evidence", [])
        evidence_text = "\n\n".join(
            f"Source: {item.source}\nCitation: [{item.citation}]\n{item.content}"
            for item in evidence
        )
        unavailable = state.get("unavailable", [])
        unavailable_text = "\n".join(f"- {item}" for item in unavailable) or "- None"
        user_prompt = (
            f"Project: {report.group_name}\n"
            f"Reporting period: {report.period_start} to {report.period_end}\n\n"
            f"Evidence:\n{evidence_text or '(No source evidence was returned.)'}\n\n"
            f"Unavailable sources:\n{unavailable_text}"
        )
        report_text = self._ollama.generate(REPORT_SYSTEM_PROMPT, user_prompt, json_mode=False).strip()
        return {"report_text": report_text}

    def _enqueue(self, state: ReportState) -> ReportState:
        report = self._reports.get(state["report_id"])
        if report is None:
            raise ValueError(f"Unknown weekly report {state['report_id']}")
        report_text = state.get("report_text", "")
        subject = f"Weekly project update - {report.report_id}"
        body = (
            f"Project: {report.group_name}\n"
            f"Period: {report.period_start} to {report.period_end}\n\n"
            f"{report_text}\n\n"
            f"Reply to this email with a question about this update."
        )
        self._reports.set_status(report.report_id, "QUEUED", report_text=report_text)
        self._outbox.enqueue(
            to_email=report.owner_email,
            subject=subject,
            body_text=body,
            job_id=report.report_id,
        )
        return state
