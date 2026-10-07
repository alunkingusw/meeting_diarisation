"""Weekly group report as a LangGraph: collect cited evidence from every source, then synthesise."""
from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from backend.config import settings
from backend.engine.report_schemas import (
    ReportAnswerRequest,
    ReportAnswerResponse,
    ReportEvidenceItem,
    WeeklyReportResponse,
)
from backend.llm.ollama_client import OllamaClient, OllamaError
from backend.models import Group, Meeting, MeetingComment
from backend.project_rag import group_service
from backend.project_rag.schemas import QueryRequest
from backend.transcript_rag.indexer import search_transcripts, transcripts_in_window

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = """You write a weekly project update using only the evidence supplied.
Do not invent events, dates, people, status, or causes. Separate the report into Meetings,
GitHub, and Trello. If a source has no evidence, say that no evidence was found. If a source
was unavailable, state that explicitly. Cite every factual statement with the supplied citation
in square brackets. Keep the email concise and plain text."""

ANSWER_SYSTEM_PROMPT = """Answer the user's question using only the weekly report evidence supplied.
Do not invent facts. Cite factual claims with the supplied evidence citation. If the evidence
does not answer the question, say so and explain which source would need a fresh lookup. You may
explain meetings, GitHub, and Trello evidence together, but keep source boundaries clear."""


class ReportState(TypedDict, total=False):
    evidence: list[ReportEvidenceItem]
    unavailable: list[str]
    report_text: str
    model: str


def _comment_author(comment: MeetingComment) -> str:
    if comment.group_member and comment.group_member.name:
        return comment.group_member.name
    if comment.user and comment.user.username:
        return comment.user.username
    return "Unknown"


def _transcript_citation(chunk: dict) -> str:
    return (
        f"{chunk.get('meeting_title')}, {chunk.get('meeting_date')}, "
        f"{chunk.get('start_ts')}-{chunk.get('end_ts')}, {chunk.get('speaker')}"
    )


def collect_meeting_evidence(
    db: Session, group: Group, since: date, until: date
) -> list[ReportEvidenceItem]:
    """Stored summaries and comments for meetings in the window; transcript chunks for meetings
    that have no summary yet."""
    meetings = (
        db.query(Meeting)
        .filter(
            Meeting.group_id == group.id,
            Meeting.date >= datetime.combine(since, time.min),
            Meeting.date < datetime.combine(until, time.min),
        )
        .order_by(Meeting.date)
        .all()
    )
    evidence: list[ReportEvidenceItem] = []
    unsummarised: set[str] = set()
    for meeting in meetings:
        day = meeting.date.date().isoformat()
        if meeting.summary and meeting.summary.strip():
            evidence.append(
                ReportEvidenceItem(
                    source="meetings", evidence_id=f"meeting-{meeting.id}-summary",
                    title=f"Meeting {day}", event_date=day, content=meeting.summary.strip(),
                    citation=f"Meeting {meeting.id}, {day}",
                )
            )
        else:
            unsummarised.add(str(meeting.id))
        if meeting.comments:
            lines = [
                f"{_comment_author(c)} ({c.created.date().isoformat()}): {c.comment.strip()}"
                for c in sorted(meeting.comments, key=lambda c: c.created)
            ]
            evidence.append(
                ReportEvidenceItem(
                    source="meetings", evidence_id=f"meeting-{meeting.id}-comments",
                    title=f"Meeting {day} comments", event_date=day, content="\n".join(lines),
                    citation=f"Meeting {meeting.id} comments, {day}",
                )
            )

    if unsummarised:
        group_name = group.name or ""
        chunks = transcripts_in_window(group_name, since, until, settings.transcript_window_chunk_limit)
        if chunks is None:
            chunks = search_transcripts(
                group_name, "meetings and decisions", settings.retrieval_top_k, since=since, until=until
            )
        for chunk in chunks:
            if str(chunk.get("meeting_id")) not in unsummarised:
                continue
            evidence.append(
                ReportEvidenceItem(
                    source="meetings", evidence_id=str(chunk.get("chunk_id")),
                    title=str(chunk.get("meeting_title")), event_date=chunk.get("meeting_date"),
                    content=chunk.get("text", ""), citation=_transcript_citation(chunk),
                )
            )
    return evidence


def collect_project_evidence(
    db: Session, group: Group, since: date, until: date
) -> tuple[list[ReportEvidenceItem], list[str]]:
    window = f"between {since.isoformat()} and {until.isoformat()}"
    questions = {
        "github": (
            f"Summarise GitHub commits, pull requests, issues, and releases {window}. "
            "Return only activity in that period with identifiers and dates."
        ),
        "trello": (
            f"Summarise Trello card movement, completed work, blockers, and due dates {window}. "
            "Return only activity in that period with card names and dates."
        ),
    }
    linked = group_service.available_sources(group)
    evidence: list[ReportEvidenceItem] = []
    unavailable: list[str] = []
    for source, question in questions.items():
        if source not in linked:
            continue
        db.rollback()
        try:
            answer = group_service.query_source(
                db, group, source, QueryRequest(question=question, since=since)
            ).answer.strip()
        except ValueError:
            repo = group_service.get_or_create_repo(db, group)
            synced = repo.last_synced_at if source == "github" else repo.trello_last_synced_at
            # Ingested but quiet this period is "no evidence", not an unavailable source.
            if synced is None:
                unavailable.append(f"{source} (nothing ingested yet)")
            continue
        except OllamaError as exc:
            unavailable.append(f"{source} ({exc})")
            continue
        if answer:
            evidence.append(
                ReportEvidenceItem(
                    source=source, evidence_id=f"group-{group.id}-{source}",
                    title=f"{source.title()} activity query", content=answer,
                    citation=f"{group.name} ({source} activity query)",
                )
            )
    return evidence, unavailable


def _format_evidence(evidence: list[ReportEvidenceItem]) -> str:
    return "\n\n".join(
        f"Source: {item.source}\nCitation: [{item.citation}]\n{item.content}" for item in evidence
    )


def build_report_graph(db: Session, group: Group, since: date, until: date):
    def collect(state: ReportState) -> ReportState:
        meetings = collect_meeting_evidence(db, group, since, until)
        project, unavailable = collect_project_evidence(db, group, since, until)
        return {"evidence": meetings + project, "unavailable": unavailable}

    def synthesise(state: ReportState) -> ReportState:
        unavailable = "\n".join(f"- {u}" for u in state["unavailable"]) or "- None"
        prompt = (
            f"Project: {group.name}\n"
            f"Reporting period: {since.isoformat()} to {until.isoformat()}\n\n"
            f"Evidence:\n{_format_evidence(state['evidence']) or '(No source evidence was returned.)'}\n\n"
            f"Unavailable sources:\n{unavailable}"
        )
        with OllamaClient() as llm:
            generated = llm.chat(system_prompt=REPORT_SYSTEM_PROMPT, user_prompt=prompt)
        return {"report_text": generated.text, "model": generated.model}

    graph = StateGraph(ReportState)
    graph.add_node("collect", collect)
    graph.add_node("synthesise", synthesise)
    graph.add_edge(START, "collect")
    graph.add_edge("collect", "synthesise")
    graph.add_edge("synthesise", END)
    return graph.compile()


def compose_weekly_report(db: Session, group: Group, since: date, until: date) -> WeeklyReportResponse:
    """Raises OllamaError if the LLM is down. Individual sources failing is reported, not raised."""
    state = build_report_graph(db, group, since, until).invoke({})
    return WeeklyReportResponse(
        group_id=group.id,
        group_name=group.name or "",
        period_start=since,
        period_end=until,
        report_text=state["report_text"],
        model=state["model"],
        evidence=state["evidence"],
        unavailable=state["unavailable"],
    )


def answer_report_question(group: Group, request: ReportAnswerRequest) -> ReportAnswerResponse:
    prompt = (
        f"Project: {group.name}\n"
        f"Reporting period: {request.period_start.isoformat()} to {request.period_end.isoformat()}\n"
        f"User question: {request.question}\n\n"
        f"Persisted evidence:\n{_format_evidence(request.evidence) or '(No evidence was persisted.)'}"
    )
    with OllamaClient() as llm:
        generated = llm.chat(system_prompt=ANSWER_SYSTEM_PROMPT, user_prompt=prompt)
    return ReportAnswerResponse(answer=generated.text, model=generated.model)
