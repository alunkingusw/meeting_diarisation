"""Read-only LangChain agents for individual project-group sources."""

from datetime import date

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from sqlalchemy.orm import Session

from backend.config import settings
from backend.engine.query_agent_schemas import (
    QuantitativeFact,
    SpecialistQueryInput,
    SpecialistQueryResult,
    TrustedQueryContext,
)
from backend.models import Group
from backend.project_rag.group_service import available_sources, query_source
from backend.project_rag.schemas import (
    ConversationQueryRequest,
    SourceQueryResponse,
    TranscriptStatsResponse,
)

_TRANSCRIPT_SYSTEM_PROMPT = (
    "You answer questions using one group's meeting transcripts. You must call "
    "retrieve_transcript_evidence exactly once before answering. Use only that result. "
    "Cite qualitative claims with stable evidence IDs in square brackets. Use the "
    "deterministic transcript statistics for quantitative claims; never estimate "
    "counts, durations, or percentages from transcript extracts. If the evidence does "
    "not answer the question, say so plainly."
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

    source_result: SourceQueryResponse | None = None

    @tool
    def retrieve_transcript_evidence() -> str:
        """Retrieve transcript evidence within the application's authorized group and filters."""
        nonlocal source_result
        db.rollback()
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
        db.rollback()
        return source_result.model_dump_json()

    agent = create_agent(
        model=ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=settings.ollama_temperature,
        ),
        tools=[retrieve_transcript_evidence],
        system_prompt=_TRANSCRIPT_SYSTEM_PROMPT,
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": request.question}]}
    )

    answer = result["messages"][-1].content.strip()
    if source_result is None:
        raise RuntimeError("Transcript specialist did not retrieve source evidence")

    return SpecialistQueryResult(
        source=source,
        question=request.question,
        answer=answer,
        quantitative_facts=_transcript_facts(context, request, source_result.transcript_stats),
        evidence=source_result.evidence,
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