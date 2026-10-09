"""Preprocess one VTT: verify, parse, chunk, compute stats, and write outputs.

The backend transcript indexer consumes the resulting chunks, embeds them, and stores them in
Chroma.
"""
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from .verify import verify_vtt
from .parsing import parse_vtt_cues
from .chunker import merge_cues_into_turns, build_chunks
from .stats import meeting_stats_summary


def process_vtt_file(
    file_path: str,
    meeting_title: str,
    meeting_date: str,
    output_dir: str = "./rag_output",
    meeting_id: str = None,
    min_speakers: int = 2,
    max_chunk_words: int = 150,
) -> dict:
    """
    Full pipeline for one VTT file:
      1. Verify speaker metadata is present and usable (raises on failure).
      2. Parse cues, merge into speaker turns.
      3. Build retrieval-ready chunks with full provenance metadata.
      4. Compute deterministic per-speaker quantitative stats.
      5. Write chunks.jsonl and stats.json to output_dir/<meeting_id>/.

    Returns a summary dict with output paths and headline numbers.
    """
    file_path = str(file_path)
    meeting_id = meeting_id or Path(file_path).stem or uuid.uuid4().hex[:8]

    # Step 1: verify — raises ValueError with details if the file is unusable
    verify_vtt(file_path, min_speakers=min_speakers, raise_on_failure=True)

    # Step 2: parse + merge
    raw_text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    cues = parse_vtt_cues(raw_text)
    turns = merge_cues_into_turns(cues)

    # Step 3: chunk (for embedding / vector store)
    chunks = build_chunks(
        cues=cues,
        meeting_id=meeting_id,
        meeting_title=meeting_title,
        meeting_date=meeting_date,
        source_file=file_path,
        max_words=max_chunk_words,
    )

    # Step 4: stats (for direct structured lookup, not embedded)
    stats = meeting_stats_summary(turns)
    stats["meeting_id"] = meeting_id
    stats["meeting_title"] = meeting_title
    stats["meeting_date"] = meeting_date
    stats["source_file"] = file_path
    stats["processed_at"] = datetime.now(timezone.utc).isoformat()

    # Step 5: write outputs
    out_dir = Path(output_dir) / meeting_id
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = out_dir / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")

    stats_path = out_dir / "stats.json"
    with stats_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return {
        "meeting_id": meeting_id,
        "chunk_count": len(chunks),
        "unique_speakers": len(stats["speakers"]),
        "chunks_path": str(chunks_path),
        "stats_path": str(stats_path),
    }


