"""Shared data structures for the VTT RAG pipeline."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Cue:
    """A single raw VTT cue after speaker/text extraction."""
    index: int
    speaker: str
    text: str
    start_ts: str      # "HH:MM:SS.mmm"
    end_ts: str
    format: str         # "voice_tag" or "label_prefix"


@dataclass
class Turn:
    """One or more contiguous cues from the same speaker, merged.
    This is the natural unit for quantitative speaker stats."""
    speaker: str
    text: str
    start_ts: str
    end_ts: str
    start_sec: float
    end_sec: float
    cue_count: int
    word_count: int


@dataclass
class Chunk:
    """A retrieval-ready unit with full provenance metadata, so the LLM
    can cite it and the user can verify against the original transcript."""
    chunk_id: str
    meeting_id: str
    meeting_title: str
    meeting_date: str
    source_file: str
    speaker: str
    text: str
    start_ts: str
    end_ts: str
    start_sec: float
    end_sec: float
    duration_sec: float
    word_count: int
    turn_index: int
    prev_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "meeting_id": self.meeting_id,
            "meeting_title": self.meeting_title,
            "meeting_date": self.meeting_date,
            "source_file": self.source_file,
            "speaker": self.speaker,
            "text": self.text,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "duration_sec": self.duration_sec,
            "word_count": self.word_count,
            "turn_index": self.turn_index,
            "prev_chunk_id": self.prev_chunk_id,
            "next_chunk_id": self.next_chunk_id,
        }

    def citation(self) -> str:
        """Human-readable citation string — use this format in your RAG
        prompt template so the local LLM references verifiable sources."""
        return (
            f"[{self.meeting_title}, {self.meeting_date}, "
            f"{self.start_ts}-{self.end_ts}, {self.speaker}]"
        )
