from __future__ import annotations

import logging
from datetime import date
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.admin.notifier import AdminCategory, AdminNotifier
from app.diarisation.client import DiarisationClient
from app.jobs.store import Outbox
from app.reports.models import ReportEvidence
from app.reports.store import ReportStore

logger = logging.getLogger(__name__)


class ReportState(TypedDict, total=False):
    report_id: str
    evidence: list[ReportEvidence]
    report_text: str
    error: Optional[str]


class WeeklyReportWorkflow:
    """Durable delivery of a weekly report: the backend composes it, the agent persists the
    evidence (so follow-up questions can be answered) and queues the email."""

    def __init__(
        self,
        report_store: ReportStore,
        outbox: Outbox,
        diarisation: DiarisationClient,
        admin: AdminNotifier,
    ):
        self._reports = report_store
        self._outbox = outbox
        self._diarisation = diarisation
        self._admin = admin
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(ReportState)
        graph.add_node("compose", self._compose)
        graph.add_node("persist", self._persist)
        graph.add_node("enqueue", self._enqueue)
        graph.add_edge(START, "compose")
        graph.add_edge("compose", "persist")
        graph.add_edge("persist", "enqueue")
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

    def _compose(self, state: ReportState) -> ReportState:
        report = self._reports.get(state["report_id"])
        if report is None:
            raise ValueError(f"Unknown weekly report {state['report_id']}")
        self._reports.set_status(report.report_id, "COLLECTING")
        token = self._diarisation.login_for_email(report.owner_email)
        composed = self._diarisation.compose_weekly_report(
            token,
            report.group_id,
            date.fromisoformat(report.period_start),
            date.fromisoformat(report.period_end),
        )
        return {"evidence": composed.evidence, "report_text": composed.report_text}

    def _persist(self, state: ReportState) -> ReportState:
        report_id = state["report_id"]
        self._reports.replace_evidence(report_id, state.get("evidence", []))
        self._reports.set_status(report_id, "SYNTHESISING")
        return state

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
