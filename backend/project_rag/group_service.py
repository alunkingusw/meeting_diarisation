"""Group-level orchestration: index sync, ingestion, and the per-source and unified query flows."""

import json
import logging
from pathlib import Path
from datetime import date, datetime, time

from sqlalchemy.orm import Session

from backend.config import settings
from backend.jobs.service import submit_job
from backend.llm.ollama_client import OllamaError, generate
from backend.models import Group, Meeting, RawFile, RawFileType
from backend.project_rag.models import Repo
from backend.project_rag.schemas import (
    EvidenceItem,
    IngestSummary,
    ProjectStatsResponse,
    QueryRequest,
    SourceName,
    SourceQueryResponse,
    TranscriptMeetingStatsResponse,
    TranscriptSpeakerStatsResponse,
    TranscriptStatsResponse,
)
from backend.project_rag.services.ingest_service import (
    clone_and_count_commits,
    flush_repo,
    ingest_repo,
)
from backend.project_rag.services.query_service import answer_question
from backend.project_rag.vectorstore import RetrievedChunk, collection_name, delete_repo_chunks
from backend.transcript_rag.indexer import (
    load_transcript_stats,
    search_transcripts,
    transcripts_in_window,
)

logger = logging.getLogger(__name__)



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


def start_ingest(
    db: Session,
    group: Group,
    sources: tuple[str, ...],
    flush: bool,
    user_id: int | None = None,
) -> IngestSummary:
    """Ingest the requested sources, inline for small repos and as a background job for large ones."""
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
        job = submit_job(
            db, "ingest",
            {"repo_id": repo.id, "local_path": str(local_path), "sources": list(sources)},
            user_id=user_id, group_id=group.id,
        )
        return IngestSummary(group_id=group.id, status="running", warnings=warnings, job_id=job.id)

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
        db, repo, request.question, since=request.since, until=request.until,
        sources=(source,), label=group.name
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
    "You answer questions about a group's recorded meetings using ONLY the transcript "
    "extracts provided for qualitative claims, and use the supplied TRANSCRIPT STATISTICS for "
    "quantitative claims. Never estimate counts, durations, or percentages from retrieved chunks. "
    "Only state a quantitative fact when statistics are marked complete for its scope; otherwise "
    "say that the metric is unavailable or incomplete. Extract headings include the meeting ID; "
    "use it to resolve meeting-specific questions, but do not include the heading index or meeting "
    "ID in citations. Cite narrative claims using only the actual title, date, time, and speaker "
    "values, for example [Release Planning, 2026-09-14, 00:00:00.000, Ada]. Never copy placeholders "
    "such as 'Meeting Title' or 'YYYY-MM-DD'. Attribute statements to the speaker who made them. "
    "If evidence does not answer the question, say so plainly rather than guessing. Keep it concise."
)


def _transcript_stats(
    db: Session,
    group: Group,
    since: date | None,
    until: date | None,
    meeting_id: int | None,
) -> TranscriptStatsResponse:
    query = (
        db.query(Meeting.id)
        .join(RawFile, RawFile.meeting_id == Meeting.id)
        .filter(
            Meeting.group_id == group.id,
            RawFile.type.in_([RawFileType.TRANSCRIPT_PROVIDED, RawFileType.TRANSCRIPT_GENERATED]),
        )
        .distinct()
    )
    if since is not None:
        query = query.filter(Meeting.date >= datetime.combine(since, time.min))
    if until is not None:
        query = query.filter(Meeting.date < datetime.combine(until, time.min))
    if meeting_id is not None:
        query = query.filter(Meeting.id == meeting_id)
    meeting_ids = sorted(row[0] for row in query.all())
    records, missing_ids = load_transcript_stats(group.id, meeting_ids)

    total_duration = sum(float(record.get("total_duration_sec", 0.0)) for record in records)
    aggregate: dict[str, dict[str, float | int]] = {}
    meeting_results: list[TranscriptMeetingStatsResponse] = []
    for record in records:
        meeting_duration = float(record.get("total_duration_sec", 0.0))
        meeting_speakers: list[TranscriptSpeakerStatsResponse] = []
        for speaker in record.get("speakers", []):
            name = str(speaker["speaker"])
            duration = float(speaker.get("total_duration_sec", 0.0))
            words = int(speaker.get("total_words", 0))
            turns = int(speaker.get("turn_count", 0))
            meeting_speakers.append(
                TranscriptSpeakerStatsResponse(
                    speaker=name,
                    total_duration_sec=duration,
                    total_words=words,
                    turn_count=turns,
                    avg_words_per_turn=float(speaker.get("avg_words_per_turn", 0.0)),
                    meeting_time_share_pct=float(speaker.get("pct_of_meeting_time", 0.0)),
                    meetings_spoken=1,
                )
            )
            totals = aggregate.setdefault(
                name, {"duration": 0.0, "words": 0, "turns": 0, "meetings": 0}
            )
            totals["duration"] += duration
            totals["words"] += words
            totals["turns"] += turns
            totals["meetings"] += 1

        meeting_results.append(
            TranscriptMeetingStatsResponse(
                meeting_id=int(record["meeting_id"]),
                meeting_title=str(record.get("meeting_title", "")),
                meeting_date=date.fromisoformat(str(record["meeting_date"])[:10]),
                total_duration_sec=meeting_duration,
                speakers=meeting_speakers,
            )
        )

    speaker_results = [
        TranscriptSpeakerStatsResponse(
            speaker=name,
            total_duration_sec=float(values["duration"]),
            total_words=int(values["words"]),
            turn_count=int(values["turns"]),
            avg_words_per_turn=(
                round(int(values["words"]) / int(values["turns"]), 1)
                if int(values["turns"]) else 0.0
            ),
            meeting_time_share_pct=(
                round(float(values["duration"]) / total_duration * 100, 1)
                if total_duration else 0.0
            ),
            meetings_spoken=int(values["meetings"]),
        )
        for name, values in sorted(
            aggregate.items(), key=lambda item: float(item[1]["duration"]), reverse=True
        )
    ]
    return TranscriptStatsResponse(
        complete=bool(meeting_ids) and not missing_ids,
        total_meetings=len(records),
        total_duration_sec=total_duration,
        missing_meeting_ids=missing_ids,
        speakers=speaker_results,
        meetings=meeting_results,
    )


def _format_transcript_hit(index: int, hit: dict) -> str:
    title = hit.get("meeting_title") or f"meeting {hit.get('meeting_id')}"
    date_part = str(hit.get("meeting_date") or "")[:10]
    return (
        f"[{index}] meeting_id={hit.get('meeting_id', '?')} | {title}, {date_part}, {hit.get('start_ts', '?')}, "
        f"{hit.get('speaker', 'unknown')}\n{hit.get('text', '')}"
    )


def _evidence_from_transcript_hit(hit: dict) -> EvidenceItem:
    return EvidenceItem(
        id=str(hit.get("chunk_id", "")),
        source_type="transcript",
        author=hit.get("speaker"),
        timestamp=hit.get("start_ts"),
        distance=hit.get("distance"),
        text=hit.get("text", ""),
        metadata={k: v for k, v in hit.items() if k not in ("text", "distance")},
    )


def _query_conversation(db: Session, group: Group, request: QueryRequest) -> SourceQueryResponse:
    since = request.since
    until = getattr(request, "until", None)
    retrieve_only = getattr(request, "retrieve_only", False)
    group_name = group.name or ""

    meeting_id = getattr(request, "meeting_id", None)

    hits = None
    if since is not None or until is not None:
        hits = transcripts_in_window(group_name, since, until, settings.transcript_window_chunk_limit)
        if hits is not None and meeting_id is not None:
            hits = [h for h in hits if str(h.get("meeting_id")) == str(meeting_id)]
    complete = hits is not None
    if hits is None:
        hits = search_transcripts(
            group_name, request.question, n_results=settings.retrieval_top_k,
            meeting_id=meeting_id, since=since, until=until,
        )
    if not hits:
        raise ValueError("No indexed meeting transcripts match this question")

    transcript_stats = _transcript_stats(db, group, since, until, meeting_id)

    if retrieve_only:
        return SourceQueryResponse(
            source="conversation",
            question=request.question,
            answer="",
            model=None,
            evidence=[_evidence_from_transcript_hit(h) for h in hits],
            complete_window=complete,
            transcript_stats=transcript_stats,
        )

    parts: list[str] = []
    used = 0
    for index, hit in enumerate(hits, start=1):
        rendered = _format_transcript_hit(index, hit)
        if used + len(rendered) > settings.max_context_chars and parts:
            break
        parts.append(rendered)
        used += len(rendered)

    generated = generate(
        CONVERSATION_SYSTEM_PROMPT,
        "TRANSCRIPT STATISTICS (deterministic; scope and completeness are explicit):\n"
        + json.dumps(transcript_stats.model_dump(mode="json"), ensure_ascii=False)
        + "\n\nTRANSCRIPT EXTRACTS:\n"
        + "\n\n".join(parts)
        + f"\n\nQUESTION: {request.question}",
    )

    kept = hits[: len(parts)]
    return SourceQueryResponse(
        source="conversation",
        question=request.question,
        answer=generated.text,
        model=generated.model,
        evidence=[_evidence_from_transcript_hit(h) for h in kept],
        truncated_evidence=len(hits) - len(kept),
        complete_window=complete and len(kept) == len(hits),
        transcript_stats=transcript_stats,
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
