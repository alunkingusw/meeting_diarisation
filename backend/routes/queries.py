# Copyright 2025 Alun King
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.auth import is_group_member, is_group_owner
from backend.db_dependency import get_db
from backend.llm.ollama_client import OllamaError
from backend.models import Group
from backend.engine.query_graph import run_unified_query
from backend.project_rag import group_service
from backend.project_rag.models import Repo
from backend.project_rag.schemas import (
    IngestStatus,
    ConversationQueryRequest,
    IngestSummary,
    ProjectStatsResponse,
    QueryRequest,
    SourceName,
    SourceQueryResponse,
    UnifiedQueryRequest,
    UnifiedQueryResponse,
)
from backend.project_rag.services.repo_stats import collect_project_stats

router = APIRouter(prefix="/groups/{group_id}", tags=["query"])


def _get_group(db: Session, group_id: int) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


def _run_source_query(
    db: Session, group_id: int, source: SourceName, payload: QueryRequest
) -> SourceQueryResponse:
    group = _get_group(db, group_id)
    try:
        return group_service.query_source(db, group, source, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/conversation/query", response_model=SourceQueryResponse)
def query_conversation(
    group_id: int,
    payload: ConversationQueryRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_member),
):
    """Answer a question from this group's meeting transcripts, with the extracts used.

    With `since`/`until` the meeting-date range is applied inside the vector store, and a small
    enough window is read in full (chronologically) rather than relevance-sampled. Set
    `retrieve_only` to get the chunks without an LLM answer."""
    return _run_source_query(db, group_id, "conversation", payload)


@router.post("/github/query", response_model=SourceQueryResponse)
def query_github(
    group_id: int,
    payload: QueryRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_member),
):
    """Answer a question from the group's ingested GitHub commits, issues and review comments."""
    return _run_source_query(db, group_id, "github", payload)


@router.post("/trello/query", response_model=SourceQueryResponse)
def query_trello(
    group_id: int,
    payload: QueryRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_member),
):
    """Answer a question from the group's ingested Trello card activity."""
    return _run_source_query(db, group_id, "trello", payload)


@router.post("/query", response_model=UnifiedQueryResponse)
def query_unified(
    group_id: int,
    payload: UnifiedQueryRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_member),
):
    """Query across sources. Without `sources`, the question is routed to the sources it needs
    and, if several are used, their answers are merged into one."""
    group = _get_group(db, group_id)
    try:
        return run_unified_query(db, group, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/stats", response_model=ProjectStatsResponse)
def group_stats(
    group_id: int,
    weeks: int = Query(default=12, ge=1, le=104),
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_member),
):
    """Facts computed from ingested GitHub/Trello data, with no LLM involved."""
    group = _get_group(db, group_id)
    repo = group_service.get_or_create_repo(db, group)
    return collect_project_stats(db, repo, weeks=weeks, label=group.name)


@router.post("/ingest", response_model=IngestSummary)
def ingest(
    group_id: int,
    background_tasks: BackgroundTasks,
    sources: list[Literal["github", "trello"]] = Query(default=["github", "trello"]),
    flush: bool = Query(
        default=False, description="Discard the selected sources' stored data and rebuild from scratch."
    ),
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_owner),
):
    """Ingest the group's linked GitHub repo and/or Trello board. Idempotent unless `flush` is set.
    Large repos are ingested in the background; poll `GET /groups/{group_id}/ingest/status`."""
    group = _get_group(db, group_id)
    if not (group.github_repo_url or group.trello_board_id):
        raise HTTPException(status_code=400, detail="Group has no GitHub repo or Trello board linked")
    try:
        return group_service.start_ingest(
            db, group, tuple(dict.fromkeys(sources)), flush, background_tasks.add_task
        )
    except group_service.IngestAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except group_service.IngestFailed as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ingest/status", response_model=IngestStatus)
def ingest_status(
    group_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_member),
):
    group = _get_group(db, group_id)
    repo: Repo = group_service.get_or_create_repo(db, group)
    return repo
