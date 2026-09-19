"""Deterministic group matching (never LLM-inferred), shared by every handler that needs to
resolve which of the sender's backend groups a request is about - submit_transcript (from an
attachment) and assess_query (from a question) alike."""
from __future__ import annotations

from typing import Optional, Union

from app.diarisation.client import GroupSummary


class Matched:
    def __init__(self, group: GroupSummary):
        self.group = group


class Ambiguous:
    def __init__(self, candidates: list[GroupSummary]):
        self.candidates = candidates


class NoMatch:
    pass


MatchResult = Union[Matched, Ambiguous, NoMatch]


def match_group(hint: Optional[str], groups: list[GroupSummary]) -> MatchResult:
    if not groups:
        return NoMatch()
    if hint:
        needle = hint.strip().lower()
        matches = [g for g in groups if g.name.strip().lower() == needle]
        if len(matches) == 1:
            return Matched(matches[0])
        if len(matches) == 0:
            return NoMatch()
        return Ambiguous(matches)
    if len(groups) == 1:
        return Matched(groups[0])
    return Ambiguous(groups)


def group_clarification_question(match: MatchResult, groups: list[GroupSummary], subject: str) -> str:
    """`subject` names what needs a group, e.g. "this transcript" or "this question"."""
    if not groups:
        return (
            f"You don't currently belong to any group in the system, so I can't tell which "
            f"group {subject} is for. Please contact the admin."
        )
    names = ", ".join(g.name for g in groups)
    return f"Which group is {subject} for? You belong to: {names}."
