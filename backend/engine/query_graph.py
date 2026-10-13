"""Parent query workflow: select authorized specialists, delegate, and compose their evidence."""
from __future__ import annotations

import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from backend.config import settings
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

COMPOSE_SYSTEM_PROMPT = (
    "You merge answers and structured evidence from specialists for one project group. Keep "
    "source boundaries clear, cite only the stable evidence IDs supplied under that source, "
    "and use quantitative facts only from the matching source's deterministic facts. Never "
    "estimate counts from sampled excerpts or combine facts with incompatible scopes. Mention "
    "any requested source listed under SOURCE FAILURES as unavailable; do not imply it was checked."
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


def _format_specialist_context(
    results: dict[str, SpecialistQueryResult],
    errors: dict[str, str],
    max_chars: int,
) -> str:
    failure_context = ""
    if errors:
        failure_lines = ["SOURCE FAILURES (requested sources that could not be checked):"]
        failure_lines.extend(f"- {source}: {message}" for source, message in errors.items())
        failure_context = "\n".join(failure_lines)

    available_chars = max(0, max_chars - len(failure_context) - (2 if failure_context else 0))
    per_source_budget = available_chars // max(1, len(results))
    sections: list[str] = []
    for source, result in results.items():
        lines = [f"SOURCE: {source}", "SPECIALIST ANSWER:", result.answer[: per_source_budget // 3]]
        lines.append("DETERMINISTIC FACTS:")
        lines.append(
            json.dumps(
                [fact.model_dump(mode="json") for fact in result.quantitative_facts],
                ensure_ascii=False,
            )
        )
        used = sum(len(line) for line in lines)
        lines.append("CITED EVIDENCE:")
        used += len(lines[-1])
        omitted = 0
        for evidence in result.evidence:
            prefix = (
                f"[{evidence.id}] {evidence.source_type} "
                f"author={evidence.author or 'unknown'} timestamp={evidence.timestamp or 'unknown'}: "
            )
            remaining = per_source_budget - used - len(prefix)
            if remaining <= 0:
                omitted += 1
                continue
            excerpt = evidence.text[:remaining]
            line = prefix + excerpt
            if len(excerpt) < len(evidence.text):
                line += " [truncated]"
                omitted += 1
            lines.append(line)
            used += len(line)
        if omitted:
            lines.append(f"Additional evidence items omitted or truncated: {omitted}")
        sections.append("\n".join(lines))
    context = "\n\n".join(sections)[:available_chars]
    if failure_context:
        context = f"{context}\n\n{failure_context}"
    return context[:max_chars]


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
            db.rollback()
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
        if len(results) == 1 and not errors:
            only = next(iter(results.values()))
            answer, model = only.answer, only.model
        else:
            source_context = _format_specialist_context(
                specialist_results, errors, settings.max_context_chars
            )
            source_question_context = "\n".join(
                f"{source}: {question}"
                for source, question in request.source_questions.items()
            )
            composed = generate(
                COMPOSE_SYSTEM_PROMPT,
                f"{source_context}\n\nQUESTION: {request.question}"
                + (
                    f"\n\nSOURCE-SPECIFIC QUESTIONS:\n{source_question_context}"
                    if source_question_context
                    else ""
                ),
            )
            answer, model = composed.text, composed.model
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
