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

"""Chunks a transcript .vtt via the vendored vtt_rag pipeline and embeds the
result into a per-group Chroma collection, so it can later be semantically
searched (see backend/routes/transcripts.py). Two call sites feed this: a
directly-uploaded .vtt (backend/routes/upload.py) and a server-transcribed
one (backend/processing/transcribe.py) - both produce the same chunk/stats
shape, so one indexing path covers both.
"""

import json
import logging
from pathlib import Path
from typing import Any

from backend.transcript_rag.vtt_rag import process_vtt_file
from backend.config import settings
from backend.transcript_rag.vectorstore import replace_meeting_chunks, search_chunks, transcripts_collection_name

logger = logging.getLogger(__name__)


def index_transcript(
    group_id: int,
    group_name: str,
    meeting_id: int,
    vtt_path: Path,
    meeting_title: str,
    meeting_date: str,
) -> dict[str, Any]:
    """Chunk `vtt_path` and upsert the chunks into this group's transcripts
    collection. Raises ValueError (from vtt_rag's own verification step) if
    the file has no usable speaker metadata - callers decide whether that
    should fail the request or just be logged (see the two call sites)."""
    output_dir = settings.EMBEDDING_DIR / "transcripts" / str(group_id)
    summary = process_vtt_file(
        file_path=str(vtt_path),
        meeting_title=meeting_title,
        meeting_date=meeting_date,
        output_dir=str(output_dir),
        meeting_id=str(meeting_id),
    )

    chunks_path = Path(summary["chunks_path"])
    chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line]

    replace_meeting_chunks(
        collection_name=transcripts_collection_name(group_name),
        meeting_id=meeting_id,
        group_id=group_id,
        chunks=chunks,
    )
    logger.info("Indexed %d transcript chunks for meeting %s (group %s)", len(chunks), meeting_id, group_id)
    return summary


def search_transcripts(
    group_name: str,
    query: str,
    n_results: int = 5,
    meeting_id: int | None = None,
) -> list[dict[str, Any]]:
    """Semantic search over one group's indexed transcript chunks. Returns
    an empty list if the group has nothing indexed yet, rather than raising."""
    return search_chunks(
        collection_name=transcripts_collection_name(group_name),
        query=query,
        n_results=n_results,
        meeting_id=meeting_id,
    )
