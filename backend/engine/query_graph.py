"""Parent query workflow: select authorized specialists, delegate, and compose their evidence."""
from __future__ import annotations

from typing import Any, TypedDict

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
from backend.models import Group, QueryConversationTurn
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
    prior_turn: dict[str, Any] | None
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
        prior_turn = None
        if request.conversation_id is not None:
            stored_turn = (
                db.query(QueryConversationTurn)
                .filter(
                    QueryConversationTurn.conversation_id == str(request.conversation_id),
                    QueryConversationTurn.user_id == user_id,
                    QueryConversationTurn.group_id == group.id,
                )
                .order_by(QueryConversationTurn.created_at.desc(), QueryConversationTurn.id.desc())
                .first()
            )
            if stored_turn is not None:
                prior_turn = {
                    "question": stored_turn.question,
                    "source_questions": dict(stored_turn.source_questions or {}),
                    "answer": stored_turn.answer,
                }
        if request.sources is not None:
            sources = list(dict.fromkeys(request.sources))
        else:
            routing_question = request.question
            if prior_turn is not None:
                previous_questions = " ".join(prior_turn["source_questions"].values())
                if not previous_questions:
                    previous_questions = prior_turn["question"]
                routing_question = (
                    f"Previous user question: {previous_questions}\n"
                    f"Current follow-up: {request.question}"
                )
            sources = infer_sources(routing_question, available)
        return {"sources": sources, "user_id": user_id, "prior_turn": prior_turn}

    def retrieve(state: UnifiedState) -> UnifiedState:
        specialist_results: dict[str, SpecialistQueryResult] = {}
        results: dict[str, SourceQueryResponse] = {}
        errors: dict[str, str] = {}
        model_errors: list[OllamaError | SpecialistModelError] = []
        prior_turn = state.get("prior_turn")
        prior_context = None
        if prior_turn is not None:
            previous_questions = "\n".join(
                f"{source}: {question}"
                for source, question in prior_turn["source_questions"].items()
            ) or prior_turn["question"]
            context_prefix = (
                "Previous conversation (reference resolution only; not evidence):\n"
                f"Previous questions: {previous_questions}\nPrevious answer: "
            )
            prior_context = (
                context_prefix + prior_turn["answer"][: max(0, 4000 - len(context_prefix))]
            )
        for source in state["sources"]:
            context = TrustedQueryContext(
                user_id=state["user_id"],
                group_id=group.id,
                allowed_sources=[source],
            )
            specialist = {
                "conversation": run_transcript_specialist,
                "github": run_github_specialist,
                "trello": run_trello_specialist,
            }[source]
            try:
                current_question = request.source_questions.get(source, request.question)
                retrieval_question = current_question
                if prior_turn is not None:
                    previous_question = (
                        prior_turn["source_questions"].get(source)
                        or prior_turn["question"]
                    )
                    separator = "\nFollow-up: "
                    previous_budget = max(
                        0, 4000 - len(current_question) - len(separator)
                    )
                    if previous_budget:
                        retrieval_question = (
                            f"{previous_question[-previous_budget:]}{separator}{current_question}"
                        )
                specialist_request = SpecialistQueryInput(
                    question=current_question,
                    retrieval_question=(
                        retrieval_question if retrieval_question != current_question else None
                    ),
                    context=prior_context,
                    filters=QueryFilters(since=request.since, until=request.until),
                )
                source_request = specialist_request.model_copy(
                    update={"question": current_question}
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
        response = UnifiedQueryResponse(
            question=request.question,
            answer=answer,
            model=model,
            conversation_id=request.conversation_id,
            sources_used=[r.source for r in results.values()],
            results=results,
            errors=errors,
        )
        if request.conversation_id is not None:
            db.add(
                QueryConversationTurn(
                    conversation_id=str(request.conversation_id),
                    user_id=state["user_id"],
                    group_id=group.id,
                    question=request.question,
                    source_questions={
                        source: request.source_questions.get(source, request.question)
                        for source in state["sources"]
                    },
                    answer=answer,
                    sources_used=response.sources_used,
                    evidence_refs={
                        source: [item.id for item in result.evidence]
                        for source, result in results.items()
                    },
                    errors=errors,
                    model=model,
                )
            )
            db.commit()
        return {"response": response}

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
