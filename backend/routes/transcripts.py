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

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any, List, Optional
from backend.db_dependency import get_db
from backend.auth import is_group_user
from backend.models import Group
from backend.transcript_rag.indexer import search_transcripts

router = APIRouter(prefix="/groups/{group_id}/transcripts", tags=["transcripts"])


class TranscriptSearchRequest(BaseModel):
    query: str
    meeting_id: Optional[int] = None


@router.post("/search")
def search(
        group_id: int,
        payload: TranscriptSearchRequest,
        db: Session = Depends(get_db),
        user_id: int = Depends(is_group_user),
    ):
    """Semantic search over this group's indexed transcript chunks (see
    backend/transcript_rag/indexer.py). Retrieval only - no LLM call - the
    caller is responsible for turning results into prose if it wants that."""
    group = db.query(Group).get(group_id)
    hits: List[dict[str, Any]] = search_transcripts(group.name, payload.query)
    if payload.meeting_id is not None:
        hits = [h for h in hits if h.get("meeting_id") == str(payload.meeting_id)]
    return {"results": hits}
