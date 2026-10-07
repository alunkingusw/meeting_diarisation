"""Group-level orchestration: index sync, ingestion, and the per-source and unified query flows."""

import logging
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from backend.config import settings
from backend.db import SessionLocal
from backend.llm.ollama_client import OllamaClient, OllamaError
from backend.models import Group, Meeting
from backend.project_rag.models import Repo
from backend.project_rag.schemas import (
    EvidenceItem,
    IngestSummary,
    ProjectStatsResponse,
    QueryRequest,
    SourceName,
    SourceQueryResponse,
    UnifiedQueryRequest,
    UnifiedQueryResponse,
)
from backend.project_rag.services.ingest_service import (
    clone_and_count_commits,
    flush_repo,
    ingest_repo,
)
from backend.project_rag.services.query_service import answer_question
from backend.project_rag.vectorstore import RetrievedChunk, collection_name, delete_repo_chunks
from backend.transcript_rag.indexer import search_transcripts

logger = logging.getLogger(__name__)

ALL_SOURCES: tuple[SourceName, ...] = ("conversation", "github", "trello")


class IngestAlreadyRunning(Exception):
    pass


class IngestFailed(Exception):
    pass


# ---------------------------------------------------------------- index sync


def available_sources(group: Group) -> list[SourceName]:
    """Sources this group can be queried on - conversation always, the others only if linked."""
    sources: list[SourceName] = ["conversation"]
    if group.github_repo_url:
        sources.append("github")
    if group.trello_board_id:
        sources.append("trello")
    return sources


def get_or_create_repo(db: Session, group: Group) -> Repo:
    """Return the group's index record, re-syncing it with the group's current links.

    Changing the repo URL or board discards that source's index, since its records
    would otherwise describe the wrong project.
    """
    repo = db.query(Repo).filter(Repo.group_id == group.id).one_or_none()
    if repo is None:
        repo = Repo(
            group_id=group.id,
            name=f"group_{group.id}",
            github_url=group.github_repo_url,
            trello_board_id=group.trello_board_id,
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        return repo

    if repo.github_url != group.github_repo_url:
        flush_repo(db, repo, ("github",))
        repo.github_url = group.github_repo_url
        repo.local_path = None
    if repo.trello_board_id != group.trello_board_id:
        flush_repo(db, repo, ("trello",))
        repo.trello_board_id = group.trello_board_id
    db.commit()
    return repo


def delete_group_index(db: Session, group_id: int) -> None:
    """Remove a group's GitHub/Trello index from Postgres and Chroma."""
    repo = db.query(Repo).filter(Repo.group_id == group_id).one_or_none()
    if repo is None:
        return
    for content in ("commits", "discussions", "trello"):
        delete_repo_chunks(collection_name(repo.namespace, content), repo.name)
    db.delete(repo)
    db.commit()


# ---------------------------------------------------------------- ingestion


def _run_ingest_in_background(repo_id: int, local_path: Path, sources: tuple[str, ...]) -> None:
    db = SessionLocal()
    try:
        repo = db.get(Repo, repo_id)
        try:
            ingest_repo(db, repo, local_path=local_path, sources=sources)
        except Exception as exc:  # noqa: BLE001 - recorded for polling
            logger.exception("Background ingest failed for repo %s", repo_id)
            db.rollback()
            repo.ingest_status = "failed"
            repo.ingest_error = str(exc)
            db.commit()
            return
        repo.ingest_status = "idle"
        repo.ingest_error = None
        db.commit()
    finally:
        db.close()


def start_ingest(
    db: Session,
    group: Group,
    sources: tuple[str, ...],
    flush: bool,
    add_background_task: Callable[..., None],
) -> IngestSummary:
    """Ingest the requested sources, inline for small repos and in the background for large ones."""
    repo = get_or_create_repo(db, group)
    if repo.ingest_status == "running":
        raise IngestAlreadyRunning("Ingestion is already running for this group")

    if flush:
        flush_repo(db, repo, sources)

    warnings: list[str] = []
    local_path: Path | None = None
    background = False
    if "github" in sources and repo.github_url:
        try:
            local_path, commit_count = clone_and_count_commits(repo)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise IngestFailed(str(exc)) from exc
        if commit_count > settings.large_repo_warning_commit_threshold:
            warnings.append(
                f"This repo has {commit_count} commits, large enough that its issue/comment "
                "history may exceed GitHub's pagination limit and be incomplete."
            )
        background = commit_count > settings.background_ingest_commit_threshold

    repo.ingest_status = "running"
    repo.ingest_error = None
    db.commit()

    if background:
        add_background_task(_run_ingest_in_background, repo.id, local_path, sources)
        return IngestSummary(group_id=group.id, status="running", warnings=warnings)

    try:
        summary = ingest_repo(db, repo, local_path=local_path, sources=sources)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        repo.ingest_status = "failed"
        repo.ingest_error = str(exc)
        db.commit()
        raise IngestFailed(str(exc)) from exc

    repo.ingest_status = "idle"
    repo.ingest_error = None
    db.commit()
    summary.warnings = warnings
    return summary


# ------------------------------------------------------------------ queries


def _evidence(chunk: RetrievedChunk) -> EvidenceItem:
    return EvidenceItem(
        id=chunk.chunk_id,
        source_type=chunk.source_type,
        author=chunk.author,
        timestamp=chunk.timestamp,
        distance=chunk.distance,
        text=chunk.text,
        metadata=chunk.metadata,
    )


def _query_provider_source(
    db: Session, group: Group, source: SourceName, request: QueryRequest
) -> SourceQueryResponse:
    repo = get_or_create_repo(db, group)
    result = answer_question(
        db, repo, request.question, since=request.since, sources=(source,)
    )
    return SourceQueryResponse(
        source=source,
        question=request.question,
        answer=result.answer,
        model=result.model,
        evidence=[_evidence(chunk) for chunk in result.sources],
        truncated_evidence=result.truncated_sources,
        complete_window=result.complete_window,
        stats=ProjectStatsResponse.model_validate(result.stats),
    )


CONVERSATION_SYSTEM_PROMPT = (
    "You answer questions about a group's recorded meetings using only the transcript "
    "extracts provided. Each extract is labelled with its meeting, speaker and time. "
    "Attribute statements to the speaker who made them. If the extracts do not answer "
    "the question, say so plainly rather than guessing. Be concise; lead with the answer."
)


def _format_transcript_hit(index: int, hit: dict) -> str:
    return (
        f"[{index}] meeting {hit.get('meeting_id')} | speaker: {hit.get('speaker', 'unknown')} | "
        f"at: {hit.get('start_ts', '?')}\n{hit.get('text', '')}"
    )


def _query_conversation(db: Session, group: Group, request: QueryRequest) -> SourceQueryResponse:
    top_k = settings.retrieval_top_k
    hits = search_transcripts(
        group.name or "", request.question, n_results=top_k * 3 if request.since else top_k
    )
    if request.since:
        start = datetime.combine(request.since, time.min)
        meeting_ids = {
            str(m.id)
            for m in db.query(Meeting).filter(Meeting.group_id == group.id, Meeting.date >= start)
        }
        hits = [h for h in hits if str(h.get("meeting_id")) in meeting_ids][:top_k]
    if not hits:
        raise ValueError("No indexed meeting transcripts match this question")

    parts: list[str] = []
    used = 0
    for index, hit in enumerate(hits, start=1):
        rendered = _format_transcript_hit(index, hit)
        if used + len(rendered) > settings.max_context_chars and parts:
            break
        parts.append(rendered)
        used += len(rendered)

    with OllamaClient() as llm:
        generated = llm.chat(
            system_prompt=CONVERSATION_SYSTEM_PROMPT,
            user_prompt="TRANSCRIPT EXTRACTS:\n" + "\n\n".join(parts) + f"\n\nQUESTION: {request.question}",
        )

    kept = hits[: len(parts)]
    return SourceQueryResponse(
        source="conversation",
        question=request.question,
        answer=generated.text,
        model=generated.model,
        evidence=[
            EvidenceItem(
                id=str(h.get("chunk_id", "")),
                source_type="transcript",
                author=h.get("speaker"),
                timestamp=h.get("start_ts"),
                distance=h.get("distance"),
                text=h.get("text", ""),
                metadata={k: v for k, v in h.items() if k not in ("text", "distance")},
            )
            for h in kept
        ],
        truncated_evidence=len(hits) - len(kept),
    )


def query_source(
    db: Session, group: Group, source: SourceName, request: QueryRequest
) -> SourceQueryResponse:
    """Answer from one source. Raises ValueError if nothing is linked/indexed, OllamaError if the LLM fails."""
    if source not in available_sources(group):
        raise ValueError(f"This group has no {source} source linked")
    if source == "conversation":
        return _query_conversation(db, group, request)
    return _query_provider_source(db, group, source, request)


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


def infer_sources(question: str, available: list[SourceName]) -> list[SourceName]:
    """Ask the LLM which of the available sources the question needs, defaulting to all of them."""
    if len(available) == 1:
        return available
    try:
        with OllamaClient() as llm:
            reply = llm.chat(
                system_prompt=ROUTER_SYSTEM_PROMPT,
                user_prompt=f"Available sources: {', '.join(available)}\nQuestion: {question}",
            ).text.lower()
    except OllamaError:
        return available
    chosen = [s for s in available if s in reply]
    return chosen or available


def query_unified(db: Session, group: Group, request: UnifiedQueryRequest) -> UnifiedQueryResponse:
    available = available_sources(group)
    if request.sources is not None:
        unavailable = [s for s in request.sources if s not in available]
        if unavailable:
            raise ValueError(f"This group has no {', '.join(unavailable)} source linked")
        sources = list(dict.fromkeys(request.sources))
    else:
        sources = infer_sources(request.question, available)

    results: dict[str, SourceQueryResponse] = {}
    errors: dict[str, str] = {}
    llm_error: OllamaError | None = None
    for source in sources:
        try:
            results[source] = query_source(db, group, source, request)
        except OllamaError as exc:
            llm_error = exc
            errors[source] = str(exc)
        except ValueError as exc:
            errors[source] = str(exc)

    if not results:
        if llm_error is not None:
            raise llm_error
        raise ValueError("; ".join(f"{s}: {e}" for s, e in errors.items()))

    if len(results) == 1:
        only = next(iter(results.values()))
        return UnifiedQueryResponse(
            question=request.question,
            answer=only.answer,
            model=only.model,
            sources_used=[only.source],
            results=results,
            errors=errors,
        )

    source_answers = "\n\n".join(f"SOURCE: {name}\n{r.answer}" for name, r in results.items())
    with OllamaClient() as llm:
        composed = llm.chat(
            system_prompt=COMPOSE_SYSTEM_PROMPT,
            user_prompt=f"{source_answers}\n\nQUESTION: {request.question}",
        )
    return UnifiedQueryResponse(
        question=request.question,
        answer=composed.text,
        model=composed.model,
        sources_used=[r.source for r in results.values()],
        results=results,
        errors=errors,
    )
