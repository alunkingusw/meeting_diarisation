"""
Quantitative speaker statistics — deterministic aggregation, not LLM/RAG
based. "Who spoke the most" is a sum over timestamps, not a semantic
retrieval question, so it's computed directly here and kept as a separate
structured artifact (stats.json) alongside the vector store, not embedded
into it.

Computed from merged Turns (before any long-turn splitting), so
percentages reflect actual speaking time and word counts, not chunk counts.
"""
from dataclasses import dataclass, field

from .models import Turn


@dataclass
class SpeakerStats:
    speaker: str
    total_duration_sec: float = 0.0
    total_words: int = 0
    turn_count: int = 0

    def to_dict(self, meeting_duration_sec: float = None) -> dict:
        d = {
            "speaker": self.speaker,
            "total_duration_sec": round(self.total_duration_sec, 1),
            "total_words": self.total_words,
            "turn_count": self.turn_count,
            "avg_words_per_turn": round(self.total_words / self.turn_count, 1) if self.turn_count else 0,
        }
        if meeting_duration_sec:
            d["pct_of_meeting_time"] = (
                round(100 * self.total_duration_sec / meeting_duration_sec, 1)
                if meeting_duration_sec > 0 else 0.0
            )
        return d


def compute_speaker_stats(turns: list[Turn]) -> dict[str, SpeakerStats]:
    """Aggregate per-speaker talk time, word count, and turn count."""
    stats: dict[str, SpeakerStats] = {}
    for turn in turns:
        s = stats.setdefault(turn.speaker, SpeakerStats(speaker=turn.speaker))
        s.total_duration_sec += (turn.end_sec - turn.start_sec)
        s.total_words += turn.word_count
        s.turn_count += 1
    return stats


def meeting_stats_summary(turns: list[Turn]) -> dict:
    """Full per-meeting summary: total duration, per-speaker breakdown with
    percentages, sorted by talk time descending. This is the structured
    table meant to sit alongside — not inside — the vector store, for
    direct lookup of 'who talked most' style questions."""
    if not turns:
        return {"total_duration_sec": 0.0, "speakers": []}

    meeting_start = min(t.start_sec for t in turns)
    meeting_end = max(t.end_sec for t in turns)
    meeting_duration = meeting_end - meeting_start

    per_speaker = compute_speaker_stats(turns)
    speakers_sorted = sorted(
        per_speaker.values(), key=lambda s: s.total_duration_sec, reverse=True
    )

    return {
        "total_duration_sec": round(meeting_duration, 1),
        "speakers": [s.to_dict(meeting_duration) for s in speakers_sorted],
    }
