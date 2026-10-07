"""Unified group query as a LangGraph: route to sources, retrieve from each, compose one answer."""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from backend.llm.ollama_client import OllamaError, generate
from backend.models import Group
from backend.project_rag import group_service
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
    "You merge answers about one project group that were each produced from a different data "
    "source. Write a single coherent answer. Keep source boundaries clear (say which source "
    "supports each point), point out where sources agree or conflict, and do not add facts "
    "that are not in the source answers."
)


class UnifiedState(TypedDict, total=False):
    sources: list[SourceName]
    results: dict[str, SourceQueryResponse]
    errors: dict[str, str]
    llm_error: OllamaError | None
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


def build_unified_graph(db: Session, group: Group, request: UnifiedQueryRequest):
    def route(state: UnifiedState) -> UnifiedState:
        available = group_service.available_sources(group)
        if request.sources is not None:
            unavailable = [s for s in request.sources if s not in available]
            if unavailable:
                raise ValueError(f"This group has no {', '.join(unavailable)} source linked")
            return {"sources": list(dict.fromkeys(request.sources))}
        return {"sources": infer_sources(request.question, available)}

    def retrieve(state: UnifiedState) -> UnifiedState:
        results: dict[str, SourceQueryResponse] = {}
        errors: dict[str, str] = {}
        llm_error: OllamaError | None = None
        for source in state["sources"]:
            # Release the read transaction so a connection idle through the previous LLM call can't go stale.
            db.rollback()
            try:
                results[source] = group_service.query_source(db, group, source, request)
            except OllamaError as exc:
                llm_error = exc
                errors[source] = str(exc)
            except ValueError as exc:
                errors[source] = str(exc)
        if not results:
            if llm_error is not None:
                raise llm_error
            raise ValueError("; ".join(f"{s}: {e}" for s, e in errors.items()))
        return {"results": results, "errors": errors}

    def compose(state: UnifiedState) -> UnifiedState:
        results, errors = state["results"], state["errors"]
        if len(results) == 1:
            only = next(iter(results.values()))
            answer, model = only.answer, only.model
        else:
            source_answers = "\n\n".join(f"SOURCE: {name}\n{r.answer}" for name, r in results.items())
            composed = generate(COMPOSE_SYSTEM_PROMPT, f"{source_answers}\n\nQUESTION: {request.question}")
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


def run_unified_query(db: Session, group: Group, request: UnifiedQueryRequest) -> UnifiedQueryResponse:
    """Raises ValueError if no source is linked or answered, OllamaError if the LLM is down."""
    return build_unified_graph(db, group, request).invoke({})["response"]
