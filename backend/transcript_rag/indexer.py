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
result into a per-group Chroma collection for semantic search through the
conversation-query workflow. Two call sites feed this: a directly-uploaded
.vtt (backend/routes/upload.py) and a server-transcribed one
(backend/processing/transcribe.py); both produce the same chunk/stats shape,
so one indexing path covers both.
"""

import json
import logging
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from backend.transcript_rag.vtt_rag import process_vtt_file
from backend.config import settings
from backend.transcript_rag.vectorstore import (
    get_chunks_in_window,
    replace_meeting_chunks,
    search_chunks,
    transcripts_collection_name,
)

logger = logging.getLogger(__name__)


def meeting_date_ts(meeting_date: str) -> int | None:
    """UTC-midnight epoch seconds for a 'YYYY-MM-DD...' meeting date, or None if unparseable.

    Chroma can only range-filter numbers, so the date string is mirrored as `meeting_ts`.
    """
    try:
        day = date.fromisoformat(str(meeting_date)[:10])
    except ValueError:
        return None
    return int(datetime.combine(day, time.min, tzinfo=timezone.utc).timestamp())


def date_to_ts(day: date | None) -> int | None:
    return None if day is None else meeting_date_ts(day.isoformat())


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
    ts = meeting_date_ts(meeting_date)
    if ts is not None:
        for chunk in chunks:
            chunk["meeting_ts"] = ts

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
    since: date | None = None,
    until: date | None = None,
) -> list[dict[str, Any]]:
    """Semantic search over one group's indexed transcript chunks, optionally limited to meetings
    dated in [since, until). Returns an empty list if nothing is indexed, rather than raising."""
    return search_chunks(
        collection_name=transcripts_collection_name(group_name),
        query=query,
        n_results=n_results,
        meeting_id=meeting_id,
        since_ts=date_to_ts(since),
        until_ts=date_to_ts(until),
    )


def transcripts_in_window(
    group_name: str, since: date | None, until: date | None, limit: int
) -> list[dict[str, Any]] | None:
    """All chunks of meetings dated in [since, until), or None if there are more than `limit`."""
    return get_chunks_in_window(
        transcripts_collection_name(group_name), date_to_ts(since), date_to_ts(until), limit
    )
