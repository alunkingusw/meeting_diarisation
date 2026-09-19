"""LangChain/Chroma storage boundary for transcript chunks."""

from functools import lru_cache
from typing import Any

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend.config import settings
from backend.transcript_rag.embeddings import LocalEmbeddings


def transcripts_collection_name(group_name: str) -> str:
    """Return the shared collection name used for a group's transcripts."""
    safe_name = group_name.strip().replace(" ", "_").lower()
    return f"{safe_name}_transcripts"


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(settings.TRANSCRIPT_CHROMA_DIR))


def get_collection_if_exists(name: str) -> Any | None:
    try:
        return get_chroma_client().get_collection(name=name)
    except Exception:
        return None


def get_vector_store(name: str) -> Chroma:
    return Chroma(
        client=get_chroma_client(),
        collection_name=name,
        embedding_function=LocalEmbeddings(),
    )


def _to_document(chunk: dict[str, Any], group_id: int) -> Document:
    metadata = {
        key: value
        for key, value in {**chunk, "group_id": group_id}.items()
        if value is not None
    }
    return Document(page_content=chunk["text"], metadata=metadata)


def replace_meeting_chunks(
    collection_name: str,
    meeting_id: int,
    group_id: int,
    chunks: list[dict[str, Any]],
) -> None:
    """Upsert current chunks and remove obsolete chunks for one meeting."""
    vector_store = get_vector_store(collection_name)
    existing_ids = set(
        vector_store._collection.get(where={"meeting_id": str(meeting_id)})["ids"]
    )
    documents = [_to_document(chunk, group_id) for chunk in chunks]
    current_ids = {document.metadata["chunk_id"] for document in documents}

    if documents:
        vector_store._collection.upsert(
            ids=[document.metadata["chunk_id"] for document in documents],
            documents=[document.page_content for document in documents],
            metadatas=[document.metadata for document in documents],
            embeddings=vector_store._embedding_function.embed_documents(
                [document.page_content for document in documents]
            ),
        )

    stale_ids = existing_ids - current_ids
    if stale_ids:
        vector_store._collection.delete(ids=list(stale_ids))


def search_chunks(
    collection_name: str,
    query: str,
    n_results: int = 5,
    meeting_id: int | None = None,
) -> list[dict[str, Any]]:
    """Search with an optional metadata filter applied inside Chroma."""
    if get_collection_if_exists(collection_name) is None:
        return []

    where = {"meeting_id": str(meeting_id)} if meeting_id is not None else None
    results = get_vector_store(collection_name).similarity_search_with_score(
        query,
        k=n_results,
        filter=where,
    )
    hits = []
    for document, distance in results:
        hit = dict(document.metadata)
        hit["distance"] = float(distance)
        hits.append(hit)
    return hits