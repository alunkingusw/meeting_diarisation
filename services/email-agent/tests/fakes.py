"""Shared in-memory test doubles."""
from __future__ import annotations

from datetime import datetime
from typing import Optional


class StubLLM:
    """Duck-type stand-in for OllamaClient: returns the same canned JSON response on every
    call (or a sequence of responses, consumed in order). `available` controls is_available()
    so tests can simulate Ollama being down."""

    def __init__(self, response, available: bool = True):
        self._responses = response if isinstance(response, list) else [response]
        self.available = available
        self.calls = 0

    def is_available(self) -> bool:
        return self.available

    def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.0, json_mode: bool = True
    ) -> str:
        response = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return response

from app.diarisation.client import (
    AttendeeSummary,
    GroupSummary,
    MeetingComment,
    MeetingSummary,
    RawFileSummary,
    TranscriptChunk,
    TransientError,
)
from app.github_raginator.client import QueryResult, RepoSummary, TransientError as GithubTransientError


class FakeDiarisationClient:
    """Duck-type stand-in for DiarisationClient - no HTTP involved. Configure `fail_on` with a
    method name to make that call raise TransientError, simulating a backend outage."""

    def __init__(
        self,
        groups: list[GroupSummary],
        member_by_name: Optional[dict[str, Optional[int]]] = None,
        fail_on: Optional[str] = None,
        transcript_chunks: Optional[list[TranscriptChunk]] = None,
    ):
        self.groups = groups
        self.transcript_chunks = transcript_chunks or []
        self.member_by_name = member_by_name or {}
        self.fail_on = fail_on
        self.meetings: list[MeetingSummary] = []
        self.uploads: list[RawFileSummary] = []
        self.attendees_added: list[int] = []
        self.comments: list[tuple[int, int, str]] = []

    def _maybe_fail(self, name: str) -> None:
        if self.fail_on == name:
            raise TransientError(f"simulated failure in {name}")

    def login(self, user_id: int) -> str:
        self._maybe_fail("login")
        return f"token-for-{user_id}"

    def login_for_email(self, email: str) -> str:
        self._maybe_fail("login_for_email")
        self._maybe_fail("login")
        return f"token-for-{email}"

    def list_groups(self, token: str) -> list[GroupSummary]:
        self._maybe_fail("list_groups")
        return self.groups

    def create_meeting(self, token: str, group_id: int, date: datetime) -> MeetingSummary:
        self._maybe_fail("create_meeting")
        meeting = MeetingSummary(id=len(self.meetings) + 1, group_id=group_id, date=date.isoformat())
        self.meetings.append(meeting)
        return meeting

    def upload_file(
        self, token: str, group_id: int, meeting_id: int, filename: str, content: bytes
    ) -> RawFileSummary:
        self._maybe_fail("upload_file")
        raw_file = RawFileSummary(
            id=len(self.uploads) + 1, file_name=filename, human_name=filename, type="transcript_provided"
        )
        self.uploads.append(raw_file)
        return raw_file

    def add_attendee(self, token: str, group_id: int, meeting_id: int, member_id: int) -> AttendeeSummary:
        self._maybe_fail("add_attendee")
        self.attendees_added.append(member_id)
        return AttendeeSummary(id=member_id, name=f"member-{member_id}")

    def add_comment(self, token: str, group_id: int, meeting_id: int, comment: str) -> MeetingComment:
        self._maybe_fail("add_comment")
        self.comments.append((group_id, meeting_id, comment))
        return MeetingComment(
            id=len(self.comments), meeting_id=meeting_id, user_id=12,
            comment=comment, created="2026-09-19T12:00:00Z",
        )

    def resolve_aliases(
        self, token: str, group_id: int, names: list[str], source: Optional[str] = None
    ) -> dict[str, Optional[int]]:
        self._maybe_fail("resolve_aliases")
        return {name: self.member_by_name.get(name) for name in names}

    def search_transcripts(
        self, token: str, group_id: int, query: str, meeting_id: Optional[int] = None
    ) -> list[TranscriptChunk]:
        self._maybe_fail("search_transcripts")
        return self.transcript_chunks


class FakeGithubRaginatorClient:
    """Duck-type stand-in for GithubRaginatorClient - no HTTP involved."""

    def __init__(
        self,
        repo_by_group_name: Optional[dict[str, RepoSummary]] = None,
        answer: str = "Alice made most of the recent commits.",
        fail_on: Optional[str] = None,
    ):
        self.repo_by_group_name = repo_by_group_name or {}
        self.answer = answer
        self.fail_on = fail_on
        self.questions_asked: list[str] = []

    def find_repo_by_group_name(self, group_name: str) -> Optional[RepoSummary]:
        if self.fail_on == "find_repo_by_group_name":
            raise GithubTransientError("simulated failure in find_repo_by_group_name")
        return self.repo_by_group_name.get(group_name)

    def query(self, repo_id: int, question: str) -> QueryResult:
        if self.fail_on == "query":
            raise GithubTransientError("simulated failure in query")
        self.questions_asked.append(question)
        return QueryResult(answer=self.answer)
