"""Local embedding adapter used by the transcript LangChain vector store."""

from functools import lru_cache

from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

from backend.config import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Load the configured SentenceTransformer model once per process."""
    return SentenceTransformer(
        settings.TRANSCRIPT_EMBEDDING_MODEL_NAME,
        device=settings.TRANSCRIPT_EMBEDDING_DEVICE,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using the local SentenceTransformer model."""
    if not texts:
        return []
    return get_embedding_model().encode(
        texts,
        show_progress_bar=False,
        convert_to_numpy=True,
    ).tolist()


class LocalEmbeddings(Embeddings):
    """Expose the existing local model through LangChain's embedding contract."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts)

    def embed_query(self, text: str) -> list[float]:
        return embed_texts([text])[0]