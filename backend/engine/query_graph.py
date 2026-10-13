"""Parent query workflow: select authorized specialists, delegate, and compose their evidence."""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from backend.engine.query_agent_schemas import (
    QueryFilters,
    SpecialistQueryResult,
    SpecialistQueryInput,
    TrustedQueryContext,
)
from backend.engine.specialists import (
    SpecialistModelError,
    run_github_specialist,
    run_transcript_specialist,
    run_trello_specialist,
    to_source_query_response,
)
from backend.llm.ollama_client import OllamaError, generate
from backend.models import Group
from backend.project_rag.group_service import available_sources
from backend.project_rag.schemas import (
    SourceName,
    SourceQueryResponse,
    UnifiedQueryRequest,
    UnifiedQueryResponse,
)

ROUTER_SYSTEM_PROMPT = (
    "Decide which data sources are needed to answer a question about a project group. "
    "Sources: conversation (what was said in meetings), github (commits, issues, code review), "
    "trello (task board cards and their movement). Reply with only the needed source names, "
    "comma-separated. If unsure, include every listed source."
)

class UnifiedState(TypedDict, total=False):
    sources: list[SourceName]
    specialist_results: dict[str, SpecialistQueryResult]
    results: dict[str, SourceQueryResponse]
    errors: dict[str, str]
    user_id: int
    response: UnifiedQueryResponse


def infer_sources(question: str, available: list[SourceName]) -> list[SourceName]:
    """Ask the LLM which of the available sources the question needs, defaulting to all of them."""
    if len(available) == 1:
        return available
    try:
        reply = generate(
            ROUTER_SYSTEM_PROMPT,
            f"Available sources: {', '.join(available)}\nQuestion: {question}",
        ).text.lower()
    except OllamaError:
        return available
    chosen = [s for s in available if s in reply]
    return chosen or available


def _compose_source_answers(
    results: dict[str, SpecialistQueryResult],
    errors: dict[str, str],
) -> str:
    sections: list[str] = []
    for source, result in results.items():
        source_label = {"github": "GitHub", "trello": "Trello"}.get(source, source.title())
        lines = [f"{source_label} findings:", result.answer.strip()]
        if result.evidence:
            evidence_ids = ", ".join(f"[{item.id}]" for item in result.evidence)
            lines.append(f"Evidence IDs: {evidence_ids}")
        sections.append("\n".join(lines))
    if errors:
        unavailable = ["Unavailable sources:"]
        unavailable.extend(f"- {source}: unavailable" for source in errors)
        sections.append("\n".join(unavailable))
    return "\n\n".join(sections)


def build_unified_graph(
    db: Session, group: Group, request: UnifiedQueryRequest, user_id: int
):
    def route(state: UnifiedState) -> UnifiedState:
        available = available_sources(group)
        if request.sources is not None:
            sources = list(dict.fromkeys(request.sources))
        else:
            sources = infer_sources(request.question, available)
        return {"sources": sources, "user_id": user_id}

    def retrieve(state: UnifiedState) -> UnifiedState:
        specialist_results: dict[str, SpecialistQueryResult] = {}
        results: dict[str, SourceQueryResponse] = {}
        errors: dict[str, str] = {}
        model_errors: list[OllamaError | SpecialistModelError] = []
        for source in state["sources"]:
            context = TrustedQueryContext(
                user_id=state["user_id"],
                group_id=group.id,
                allowed_sources=[source],
            )
            specialist_request = SpecialistQueryInput(
                question=request.question,
                filters=QueryFilters(since=request.since, until=request.until),
            )
            specialist = {
                "conversation": run_transcript_specialist,
                "github": run_github_specialist,
                "trello": run_trello_specialist,
            }[source]
            try:
                source_request = specialist_request.model_copy(
                    update={
                        "question": request.source_questions.get(source, request.question)
                    }
                )
                specialist_result = specialist(db, context, source_request)
                specialist_results[source] = specialist_result
                results[source] = to_source_query_response(specialist_result)
            except (OllamaError, SpecialistModelError, PermissionError, ValueError) as exc:
                errors[source] = str(exc)
                if isinstance(exc, (OllamaError, SpecialistModelError)):
                    model_errors.append(exc)
        if not results:
            if model_errors:
                raise model_errors[0]
            raise ValueError("; ".join(f"{s}: {e}" for s, e in errors.items()))
        return {
            "specialist_results": specialist_results,
            "results": results,
            "errors": errors,
        }

    def compose(state: UnifiedState) -> UnifiedState:
        specialist_results = state["specialist_results"]
        results, errors = state["results"], state["errors"]
        answer = _compose_source_answers(specialist_results, errors)
        models = {result.model for result in specialist_results.values() if result.model}
        model = next(iter(models)) if len(models) == 1 else None
        return {
            "response": UnifiedQueryResponse(
                question=request.question,
                answer=answer,
                model=model,
                sources_used=[r.source for r in results.values()],
                results=results,
                errors=errors,
            )
        }

    graph = StateGraph(UnifiedState)
    graph.add_node("route", route)
    graph.add_node("retrieve", retrieve)
    graph.add_node("compose", compose)
    graph.add_edge(START, "route")
    graph.add_edge("route", "retrieve")
    graph.add_edge("retrieve", "compose")
    graph.add_edge("compose", END)
    return graph.compile()


def run_unified_query(
    db: Session, group: Group, request: UnifiedQueryRequest, user_id: int
) -> UnifiedQueryResponse:
    """Raises ValueError if no source is linked or answered, OllamaError if the LLM is down."""
    return build_unified_graph(db, group, request, user_id).invoke({})["response"]
