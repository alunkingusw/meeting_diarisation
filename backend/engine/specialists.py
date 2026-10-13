"""Read-only LangChain agents for individual project-group sources."""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from sqlalchemy.orm import Session
from typing import Literal

from backend.config import settings
from backend.engine.query_agent_schemas import (
    QuantitativeFact,
    SpecialistQueryInput,
    SpecialistQueryResult,
    TrustedQueryContext,
)
from backend.llm.ollama_client import OllamaError
from backend.models import Group
from backend.project_rag.group_service import available_sources, query_source
from backend.project_rag.models import Repo
from backend.project_rag.schemas import (
    ConversationQueryRequest,
    EvidenceItem,
    ProjectStatsResponse,
    SourceQueryResponse,
    TranscriptStatsResponse,
)
from backend.project_rag.services.query_service import retrieve_question


class SpecialistModelError(RuntimeError):
    """A source specialist could not complete its model invocation."""


def to_source_query_response(result: SpecialistQueryResult) -> SourceQueryResponse:
    """Adapt the richer specialist result to the stable source-query API contract."""
    return SourceQueryResponse(
        source=result.source,
        question=result.question,
        answer=result.answer,
        model=result.model,
        evidence=result.evidence,
        truncated_evidence=result.truncated_evidence,
        complete_window=result.complete_window,
        stats=result.stats,
        transcript_stats=result.transcript_stats,
    )


def _invoke_agent(agent, question: str, source: str) -> str:
    try:
        result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    except (OllamaError, PermissionError, ValueError):
        raise
    except Exception as exc:  # noqa: BLE001 - provider errors vary by LangChain integration
        raise SpecialistModelError(f"{source.title()} specialist failed: {exc}") from exc
    messages = result.get("messages", [])
    if not messages or not isinstance(messages[-1].content, str):
        raise SpecialistModelError(f"{source.title()} specialist returned no answer")
    return messages[-1].content.strip()

_TRANSCRIPT_SYSTEM_PROMPT = (
    "You answer questions using one group's meeting transcripts. You must call "
    "retrieve_transcript_evidence exactly once before answering. Use only that result. "
    "Cite qualitative claims with stable evidence IDs in square brackets. Use the "
    "deterministic transcript statistics for quantitative claims; never estimate "
    "counts, durations, or percentages from transcript extracts. If the evidence does "
    "not answer the question, say so plainly."
)
_PROJECT_SYSTEM_PROMPT = (
    "You answer questions from one group's GitHub or Trello data. You must call "
    "retrieve_project_evidence exactly once before answering. Use only the returned "
    "evidence and deterministic stats. Do not estimate counts from excerpts. Cite "
    "qualitative claims with stable evidence IDs in square brackets. If the evidence "
    "does not answer the question, say so plainly. The returned answer field is a "
    "draft from a legacy query path; do not treat it as evidence."
)


def _ollama_chat_model() -> ChatOllama:
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=settings.ollama_temperature,
    )


def _query_scope(
    context: TrustedQueryContext, filters: SpecialistQueryInput
) -> dict[str, str | int | float]:
    scope: dict[str, str | int | float] = {"group_id": context.group_id}
    if filters.filters.since is not None:
        scope["since"] = filters.filters.since.isoformat()
    if filters.filters.until is not None:
        scope["until"] = filters.filters.until.isoformat()
    if filters.filters.meeting_id is not None:
        scope["meeting_id"] = filters.filters.meeting_id
    return scope


def _transcript_facts(
    context: TrustedQueryContext,
    request: SpecialistQueryInput,
    stats: TranscriptStatsResponse | None,
) -> list[QuantitativeFact]:
    if stats is None:
        return []

    completeness = "complete" if stats.complete else "unknown"
    provenance = [f"transcript_stats:group={context.group_id}"]
    base_scope = _query_scope(context, request)
    facts = [
        QuantitativeFact(
            name="total_meetings",
            value=stats.total_meetings,
            unit="meetings",
            scope=base_scope,
            provenance=provenance,
            completeness=completeness,
        ),
        QuantitativeFact(
            name="total_duration",
            value=stats.total_duration_sec,
            unit="seconds",
            scope=base_scope,
            provenance=provenance,
            completeness=completeness,
        ),
    ]
    for speaker in stats.speakers:
        speaker_scope = {**base_scope, "speaker": speaker.speaker}
        for name, value, unit in (
            ("speaker_duration", speaker.total_duration_sec, "seconds"),
            ("speaker_words", speaker.total_words, "words"),
            ("speaker_turns", speaker.turn_count, "turns"),
            ("speaker_average_words_per_turn", speaker.avg_words_per_turn, "words per turn"),
            ("speaker_meeting_time_share", speaker.meeting_time_share_pct, "percent"),
            ("speaker_meetings_spoken", speaker.meetings_spoken, "meetings"),
        ):
            facts.append(
                QuantitativeFact(
                    name=name,
                    value=value,
                    unit=unit,
                    scope=speaker_scope,
                    provenance=provenance,
                    completeness=completeness,
                )
            )
    return facts


def _project_facts(
    context: TrustedQueryContext,
    request: SpecialistQueryInput,
    source: str,
    stats: ProjectStatsResponse | None,
) -> list[QuantitativeFact]:
    if stats is None:
        return []

    scope: dict[str, str | int | float] = {"group_id": context.group_id, "source": source}
    if request.filters.since is not None:
        scope["since"] = request.filters.since.isoformat()
    if request.filters.until is not None:
        scope["until"] = request.filters.until.isoformat()
    provenance = [f"project_stats:repo={stats.repo_id}"]
    facts: list[QuantitativeFact] = []

    def add_fact(name: str, value: int | float, unit: str, fact_scope=scope) -> None:
        facts.append(
            QuantitativeFact(
                name=name,
                value=value,
                unit=unit,
                scope=fact_scope,
                provenance=provenance,
                completeness="complete",
            )
        )

    if source == "github":
        for name, value, unit in (
            ("commits", stats.total_commits, "commits"),
            ("issues", stats.total_issues, "issues"),
            ("open_issues", stats.open_issues, "issues"),
            ("closed_issues", stats.closed_issues, "issues"),
            ("issue_comments", stats.total_issue_comments, "comments"),
            ("review_comments", stats.total_review_comments, "comments"),
        ):
            add_fact(name, value, unit)
        contributor_metrics = (
            ("commits", "commits", "commits"),
            ("additions", "additions", "lines"),
            ("deletions", "deletions", "lines"),
            ("issues_opened", "issues_opened", "issues"),
            ("issue_comments", "issue_comments", "comments"),
            ("review_comments", "review_comments", "comments"),
        )
    else:
        add_fact("trello_actions", stats.total_trello_actions, "actions")
        contributor_metrics = (("trello_actions", "trello_actions", "actions"),)

    for contributor in stats.contributors:
        contributor_scope = {**scope, "contributor": contributor.name}
        for attribute, name, unit in contributor_metrics:
            add_fact(name, getattr(contributor, attribute), unit, contributor_scope)
    return facts


def run_transcript_specialist(
    db: Session,
    context: TrustedQueryContext,
    request: SpecialistQueryInput,
) -> SpecialistQueryResult:
    """Answer from authorized transcript evidence and deterministic transcript statistics."""
    source = "conversation"
    if source not in context.allowed_sources:
        raise PermissionError("Transcript source is not authorized for this query")

    group = db.get(Group, context.group_id)
    if group is None:
        raise ValueError("The authorized group no longer exists")
    if source not in available_sources(group):
        raise ValueError("This group has no transcript source linked")

    try:
        source_result = query_source(
            db,
            group,
            source,
            ConversationQueryRequest(
                question=request.question,
                since=request.filters.since,
                until=request.filters.until,
                meeting_id=request.filters.meeting_id,
                retrieve_only=True,
            ),
        )
    finally:
        db.rollback()

    @tool
    def retrieve_transcript_evidence() -> str:
        """Retrieve transcript evidence within the application's authorized group and filters."""
        return source_result.model_dump_json()

    agent = create_agent(
        model=_ollama_chat_model(),
        tools=[retrieve_transcript_evidence],
        system_prompt=_TRANSCRIPT_SYSTEM_PROMPT,
    )
    answer = _invoke_agent(agent, request.question, source)

    return SpecialistQueryResult(
        source=source,
        question=request.question,
        answer=answer,
        quantitative_facts=_transcript_facts(context, request, source_result.transcript_stats),
        evidence=source_result.evidence,
        truncated_evidence=source_result.truncated_evidence,
        complete_window=source_result.complete_window,
        transcript_stats=source_result.transcript_stats,
        model=settings.ollama_model,
        retrieval_metadata={
            "evidence_count": len(source_result.evidence),
            "complete_window": source_result.complete_window,
            "transcript_stats_complete": (
                source_result.transcript_stats.complete
                if source_result.transcript_stats is not None
                else False
            ),
        },
    )


def _run_project_specialist(
    db: Session,
    context: TrustedQueryContext,
    request: SpecialistQueryInput,
    source: Literal["github", "trello"],
) -> SpecialistQueryResult:
    if source not in context.allowed_sources:
        raise PermissionError(f"{source.title()} source is not authorized for this query")
    if request.filters.meeting_id is not None:
        raise ValueError("Meeting filters are only supported for transcript queries")

    group = db.get(Group, context.group_id)
    if group is None:
        raise ValueError("The authorized group no longer exists")
    if source not in available_sources(group):
        raise ValueError(f"This group has no {source} source linked")

    try:
        repo = db.query(Repo).filter(Repo.group_id == group.id).one_or_none()
        if repo is None:
            raise ValueError(f"No ingested {source} activity for this group. Ingest it first.")
        retrieved = retrieve_question(
            db,
            repo,
            request.question,
            since=request.filters.since,
            until=request.filters.until,
            sources=(source,),
            label=group.name,
        )
        source_result = SourceQueryResponse(
            source=source,
            question=request.question,
            answer="",
            evidence=[
                EvidenceItem(
                    id=chunk.chunk_id,
                    source_type=chunk.source_type,
                    author=chunk.author,
                    timestamp=chunk.timestamp,
                    distance=chunk.distance,
                    text=chunk.text,
                    metadata=chunk.metadata,
                )
                for chunk in retrieved.sources
            ],
            truncated_evidence=retrieved.truncated_sources,
            complete_window=retrieved.complete_window,
            stats=ProjectStatsResponse.model_validate(retrieved.stats),
        )
    finally:
        db.rollback()

    @tool
    def retrieve_project_evidence() -> str:
        """Retrieve this source's evidence and deterministic stats within trusted filters."""
        return source_result.model_dump_json()

    agent = create_agent(
        model=_ollama_chat_model(),
        tools=[retrieve_project_evidence],
        system_prompt=_PROJECT_SYSTEM_PROMPT,
    )
    answer = _invoke_agent(agent, request.question, source)

    return SpecialistQueryResult(
        source=source,
        question=request.question,
        answer=answer,
        quantitative_facts=_project_facts(context, request, source, source_result.stats),
        evidence=source_result.evidence,
        truncated_evidence=source_result.truncated_evidence,
        complete_window=source_result.complete_window,
        stats=source_result.stats,
        model=settings.ollama_model,
        retrieval_metadata={
            "evidence_count": len(source_result.evidence),
            "complete_window": source_result.complete_window,
            "repo_id": source_result.stats.repo_id if source_result.stats else 0,
        },
    )


def run_github_specialist(
    db: Session,
    context: TrustedQueryContext,
    request: SpecialistQueryInput,
) -> SpecialistQueryResult:
    """Answer from authorized GitHub evidence and database aggregates."""
    return _run_project_specialist(db, context, request, "github")


def run_trello_specialist(
    db: Session,
    context: TrustedQueryContext,
    request: SpecialistQueryInput,
) -> SpecialistQueryResult:
    """Answer from authorized Trello evidence and database aggregates."""
    return _run_project_specialist(db, context, request, "trello")