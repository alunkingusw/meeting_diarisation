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
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from backend.config import settings
from backend.transcript_rag.vtt_rag import process_vtt_file

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_chroma_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(settings.TRANSCRIPT_CHROMA_DIR))


@lru_cache(maxsize=1)
def _get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(
        settings.TRANSCRIPT_EMBEDDING_MODEL_NAME, device=settings.TRANSCRIPT_EMBEDDING_DEVICE
    )


def _embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_embedding_model()
    return model.encode(texts, show_progress_bar=False, convert_to_numpy=True).tolist()


def transcripts_collection_name(group_name: str) -> str:
    """One Chroma collection per group, named to match GitHub-RAGinator's
    `{group}_commits`/`{group}_discussions`/`{group}_trello` convention."""
    safe_name = group_name.strip().replace(" ", "_").lower()
    return f"{safe_name}_transcripts"


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
    if not chunks:
        return summary

    collection = _get_chroma_client().get_or_create_collection(
        name=transcripts_collection_name(group_name)
    )
    documents = [c["text"] for c in chunks]
    collection.upsert(
        ids=[c["chunk_id"] for c in chunks],
        documents=documents,
        metadatas=[{**c, "group_id": group_id} for c in chunks],
        embeddings=_embed_texts(documents),
    )
    logger.info("Indexed %d transcript chunks for meeting %s (group %s)", len(chunks), meeting_id, group_id)
    return summary


def search_transcripts(group_name: str, query: str, n_results: int = 5) -> list[dict[str, Any]]:
    """Semantic search over one group's indexed transcript chunks. Returns
    an empty list if the group has nothing indexed yet, rather than raising."""
    client = _get_chroma_client()
    try:
        collection = client.get_collection(name=transcripts_collection_name(group_name))
    except Exception:
        return []

    result = collection.query(query_embeddings=_embed_texts([query]), n_results=n_results)
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    hits = []
    for index, metadata in enumerate(metadatas):
        hit = dict(metadata)
        hit["distance"] = float(distances[index]) if index < len(distances) else None
        hits.append(hit)
    return hits
