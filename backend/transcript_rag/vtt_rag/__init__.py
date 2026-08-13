"""
vtt_rag — VTT transcript parsing, verification, chunking, and speaker
statistics for building a metadata-rich, verifiable RAG pipeline over
meeting transcripts.

Typical usage:

    from vtt_rag import process_vtt_file

    result = process_vtt_file(
        file_path="meeting.vtt",
        meeting_title="Product Sync",
        meeting_date="2026-07-09",
        output_dir="./rag_output",
    )

See README.md for the full pipeline description and embed_stub.py for an
example of indexing the resulting chunks into a local vector store.
"""

from .verify import verify_vtt, VTTVerificationResult
from .parsing import parse_vtt_cues, extract_speaker_and_text
from .chunker import merge_cues_into_turns, build_chunks, chunk_vtt_file
from .stats import compute_speaker_stats, meeting_stats_summary, SpeakerStats
from .models import Cue, Turn, Chunk
from .pipeline import process_vtt_file, process_vtt_directory

__all__ = [
    "verify_vtt",
    "VTTVerificationResult",
    "parse_vtt_cues",
    "extract_speaker_and_text",
    "merge_cues_into_turns",
    "build_chunks",
    "chunk_vtt_file",
    "compute_speaker_stats",
    "meeting_stats_summary",
    "SpeakerStats",
    "Cue",
    "Turn",
    "Chunk",
    "process_vtt_file",
    "process_vtt_directory",
]
