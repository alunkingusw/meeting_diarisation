"""Add the numeric `meeting_ts` to transcript chunks indexed before date-range filtering existed.

Run from the repo root: python -m scripts.backfill_transcript_dates
"""
from __future__ import annotations

from backend.transcript_rag.indexer import meeting_date_ts
from backend.transcript_rag.vectorstore import get_chroma_client

BATCH = 500


def main() -> None:
    client = get_chroma_client()
    updated = skipped = 0
    for collection in client.list_collections():
        name = getattr(collection, "name", collection)
        if not name.endswith("_transcripts"):
            continue
        collection = client.get_collection(name)
        offset = 0
        while True:
            page = collection.get(limit=BATCH, offset=offset, include=["metadatas"])
            if not page["ids"]:
                break
            ids, metadatas = [], []
            for chunk_id, metadata in zip(page["ids"], page["metadatas"]):
                if "meeting_ts" in metadata:
                    continue
                ts = meeting_date_ts(metadata.get("meeting_date", ""))
                if ts is None:
                    skipped += 1
                    continue
                ids.append(chunk_id)
                metadatas.append({**metadata, "meeting_ts": ts})
            if ids:
                collection.update(ids=ids, metadatas=metadatas)
                updated += len(ids)
            offset += BATCH
    print(f"Updated {updated} chunks; {skipped} had no parseable meeting_date.")


if __name__ == "__main__":
    main()
