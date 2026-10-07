"""GitHub/Trello chunk storage on the shared Chroma instance, one collection per (group, content type)."""

from dataclasses import dataclass
from typing import Any

from backend.project_rag.chunking.types import Chunk
from backend.transcript_rag.vectorstore import get_collection_if_exists, get_vector_store

# Chroma rejects a single upsert above its configured maximum, so writes are batched.
UPSERT_BATCH_SIZE = 500


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    # Chroma returns a distance (lower = more similar), not a similarity score.
    distance: float

    @property
    def source_type(self) -> str:
        return str(self.metadata.get("source_type", "unknown"))

    @property
    def author(self) -> str:
        return str(self.metadata.get("author", "unknown"))

    @property
    def timestamp(self) -> str:
        return str(self.metadata.get("timestamp", ""))


def collection_name(namespace: str, content_type: str) -> str:
    """Name for a group's collection of one content type: commits, discussions or trello."""
    return f"{namespace}_{content_type}"


def add_chunks(name: str, chunks: list[Chunk]) -> None:
    """Upsert chunks; ids are repo-scoped so re-ingesting overwrites rather than duplicates."""
    if not chunks:
        return

    vector_store = get_vector_store(name)
    for start in range(0, len(chunks), UPSERT_BATCH_SIZE):
        documents = [chunk.to_document() for chunk in chunks[start : start + UPSERT_BATCH_SIZE]]
        vector_store._collection.upsert(
            ids=[document.metadata["chunk_id"] for document in documents],
            documents=[document.page_content for document in documents],
            metadatas=[document.metadata for document in documents],
            embeddings=vector_store._embedding_function.embed_documents(
                [document.page_content for document in documents]
            ),
        )


def delete_repo_chunks(name: str, repo_name: str) -> None:
    collection = get_collection_if_exists(name)
    if collection is not None:
        collection.delete(where={"repo_name": repo_name})


def search(
    name: str,
    query_text: str,
    n_results: int = 5,
    where: dict | None = None,
) -> list[RetrievedChunk]:
    if get_collection_if_exists(name) is None:
        return []

    results = get_vector_store(name).similarity_search_with_score(
        query_text, k=n_results, filter=where
    )
    return [
        RetrievedChunk(
            chunk_id=str(document.metadata.get("chunk_id", "")),
            text=document.page_content,
            metadata={k: v for k, v in document.metadata.items() if k != "chunk_id"},
            distance=float(score),
        )
        for document, score in results
    ]
