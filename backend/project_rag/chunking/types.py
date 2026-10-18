"""Shared data structure for a chunk of text destined for Chroma."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from langchain_core.documents import Document


def _slug(value: str) -> str:
    """Normalise a value for safe use inside a Chroma id."""
    return re.sub(r"[^a-zA-Z0-9_.\-]", "_", value)


@dataclass
class Chunk:
    """
    A single unit of text to embed and store in Chroma.

    `metadata` carries everything needed for metadata-first filtering in
    Chroma (author, timestamp, source type). Retrieval here is
    metadata-first, semantic-search-second, since questions like "show me
    Student A's contributions in week 3" are filter queries, not
    similarity queries.

    `source_type` and `source_id` together let a chunk be traced back to
    its originating Postgres row (e.g. source_type="commit", source_id=<sha>).
    """

    text: str
    source_type: str  # "commit" | "issue" | "issue_comment" | "review_comment" | "trello_action"
    source_id: str
    author: str
    timestamp: datetime
    repo_name: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        """
        Stable, globally unique id for this chunk - also the Postgres
        `chroma_id` join key.

        `repo_name` has to be part of the id. A Chroma collection is shared
        by every repo in a group, and ids like "issue:1" are only unique
        *within* one repo - two repos in the same group would otherwise
        collide and silently overwrite each other on upsert.
        """
        return f"{_slug(self.repo_name)}:{self.source_type}:{_slug(self.source_id)}"

    def chroma_metadata(self) -> dict[str, Any]:
        """
        Flatten this chunk's fields into a Chroma-compatible metadata dict.

        Chroma metadata values must be str/int/float/bool - nested dicts
        are not supported, so `metadata` extras are merged in flat rather
        than nested.
        """
        base = {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "author": self.author,
            "timestamp": self.timestamp.isoformat(),
            "repo_name": self.repo_name,
        }
        base.update(self.metadata)
        return base

    def to_document(self) -> Document:
        """Convert this domain chunk to LangChain's document contract."""
        return Document(
            page_content=self.text,
            metadata={"chunk_id": self.chunk_id, **self.chroma_metadata()},
        )
