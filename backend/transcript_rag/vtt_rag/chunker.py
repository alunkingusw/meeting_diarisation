"""
Turn-merging and chunk-building for VTT transcripts.

Chunking strategy:
  1. Merge contiguous cues from the same speaker into "turns" — raw VTT
     cues are often just caption-length fragments.
  2. Split turns that exceed max_words into sub-pieces by sentence, keeping
     speaker and (interpolated) timestamp metadata attached to each piece.
  3. Never merge two different speakers into a single chunk — attribution
     is the whole point of this pipeline.
  4. Link each chunk to its neighbours (prev/next chunk_id) so retrieval
     can pull surrounding context without duplicating text into the
     embedding itself.
"""
import re
import uuid

from .models import Cue, Turn, Chunk
from .parsing import parse_vtt_cues
from .utils import timestamp_to_seconds

SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')


def merge_cues_into_turns(cues: list[Cue]) -> list[Turn]:
    """Merge consecutive cues from the same speaker into single turns.
    This is the natural unit for quantitative speaker stats — compute
    those from turns, before any long-turn splitting below."""
    if not cues:
        return []

    turns: list[Turn] = []
    current_speaker = cues[0].speaker
    current_texts = [cues[0].text]
    start_ts = cues[0].start_ts
    end_ts = cues[0].end_ts
    cue_count = 1

    def flush():
        text = " ".join(current_texts).strip()
        turns.append(Turn(
            speaker=current_speaker,
            text=text,
            start_ts=start_ts,
            end_ts=end_ts,
            start_sec=timestamp_to_seconds(start_ts),
            end_sec=timestamp_to_seconds(end_ts),
            cue_count=cue_count,
            word_count=len(text.split()),
        ))

    for cue in cues[1:]:
        if cue.speaker == current_speaker:
            current_texts.append(cue.text)
            end_ts = cue.end_ts
            cue_count += 1
        else:
            flush()
            current_speaker = cue.speaker
            current_texts = [cue.text]
            start_ts = cue.start_ts
            end_ts = cue.end_ts
            cue_count = 1

    flush()
    return turns


def _split_long_turn(turn: Turn, max_words: int) -> list[Turn]:
    """Split an overlong turn into smaller same-speaker pieces by sentence.
    Timestamps are interpolated proportionally by word count — an
    approximation, since VTT cues don't give per-sentence timing, but close
    enough for a user to locate the right area of the recording."""
    if turn.word_count <= max_words:
        return [turn]

    sentences = SENTENCE_SPLIT_RE.split(turn.text)
    if len(sentences) <= 1:
        return [turn]  # can't split further sensibly; leave as one oversized piece

    total_words = turn.word_count
    total_span = turn.end_sec - turn.start_sec
    pieces: list[Turn] = []
    buffer: list[str] = []
    buffer_words = 0
    words_before = 0

    def flush_piece(words_before_piece: int, words_in_piece: int):
        text = " ".join(buffer).strip()
        frac_start = words_before_piece / total_words if total_words else 0
        frac_end = (words_before_piece + words_in_piece) / total_words if total_words else 1
        piece_start_sec = turn.start_sec + frac_start * total_span
        piece_end_sec = turn.start_sec + frac_end * total_span
        pieces.append(Turn(
            speaker=turn.speaker,
            text=text,
            start_ts=turn.start_ts,   # original turn bounds kept for display;
            end_ts=turn.end_ts,       # start_sec/end_sec below are the precise values
            start_sec=piece_start_sec,
            end_sec=piece_end_sec,
            cue_count=turn.cue_count,
            word_count=words_in_piece,
        ))

    for sentence in sentences:
        w = len(sentence.split())
        if buffer_words + w > max_words and buffer:
            flush_piece(words_before, buffer_words)
            words_before += buffer_words
            buffer, buffer_words = [], 0
        buffer.append(sentence)
        buffer_words += w

    if buffer:
        flush_piece(words_before, buffer_words)

    return pieces


def build_chunks(
    cues: list[Cue],
    meeting_id: str,
    meeting_title: str,
    meeting_date: str,
    source_file: str,
    max_words: int = 150,
) -> list[Chunk]:
    """Full pipeline: cues -> turns -> (split if needed) -> linked Chunks."""
    turns = merge_cues_into_turns(cues)

    all_pieces: list[Turn] = []
    for turn in turns:
        all_pieces.extend(_split_long_turn(turn, max_words))

    chunks: list[Chunk] = []
    for i, piece in enumerate(all_pieces):
        chunk_id = f"{meeting_id}_{i:05d}_{uuid.uuid4().hex[:8]}"
        chunks.append(Chunk(
            chunk_id=chunk_id,
            meeting_id=meeting_id,
            meeting_title=meeting_title,
            meeting_date=meeting_date,
            source_file=source_file,
            speaker=piece.speaker,
            text=piece.text,
            start_ts=piece.start_ts,
            end_ts=piece.end_ts,
            start_sec=piece.start_sec,
            end_sec=piece.end_sec,
            duration_sec=piece.end_sec - piece.start_sec,
            word_count=piece.word_count,
            turn_index=i,
        ))

    # Link prev/next chunk ids so retrieval can pull surrounding context
    for i, chunk in enumerate(chunks):
        chunk.prev_chunk_id = chunks[i - 1].chunk_id if i > 0 else None
        chunk.next_chunk_id = chunks[i + 1].chunk_id if i < len(chunks) - 1 else None

    return chunks


def chunk_vtt_file(
    file_path: str,
    meeting_id: str,
    meeting_title: str,
    meeting_date: str,
    max_words: int = 150,
) -> list[Chunk]:
    """Convenience wrapper: read + parse + chunk a VTT file in one call.
    Run verify_vtt(file_path) beforehand — this function assumes the file
    has already passed verification."""
    from pathlib import Path
    raw_text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    cues = parse_vtt_cues(raw_text)
    return build_chunks(
        cues=cues,
        meeting_id=meeting_id,
        meeting_title=meeting_title,
        meeting_date=meeting_date,
        source_file=str(file_path),
        max_words=max_words,
    )
