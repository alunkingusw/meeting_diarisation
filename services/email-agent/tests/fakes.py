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
        self.last_user_prompt: Optional[str] = None

    def is_available(self) -> bool:
        return self.available

    def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.0, json_mode: bool = True
    ) -> str:
        self.last_user_prompt = user_prompt
        response = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return response

from app.diarisation.client import (
    AttendeeSummary,
    GroupSummary,
    MeetingComment,
    MeetingSummary,
    BackendJob,
    JobCancelledError,
    NotFoundError,
    QueryAnswer,
    RawFileSummary,
    WeeklyReportResult,
    TranscriptChunk,
    TransientError,
)


class FakeDiarisationClient:
    """Duck-type stand-in for DiarisationClient - no HTTP involved. Configure `fail_on` with a
    method name to make that call raise TransientError, simulating a backend outage."""

    def __init__(
        self,
        groups: list[GroupSummary],
        member_by_name: Optional[dict[str, Optional[int]]] = None,
        fail_on: Optional[str] = None,
        transcript_chunks: Optional[list[TranscriptChunk]] = None,
        source_answers: Optional[dict[str, str]] = None,
        unlinked_sources: Optional[set[str]] = None,
    ):
        # source -> canned answer; a source in `unlinked_sources` raises NotFoundError like the backend's 404.
        self.backend_jobs: dict[str, BackendJob] = {}
        self.cancelled_backend_jobs: list[str] = []
        self.announced_jobs: list[str] = []
        self.cancel_queries = False
        self.composed_reports: list = []
        self.report_questions: list = []
        self.report_text = "The team agreed to ship. [Planning]"
        self.report_evidence: list = []
        self.report_answer = "The team agreed to ship. [Planning]"
        self.source_answers = source_answers or {}
        self.unlinked_sources = unlinked_sources or set()
        self.queries: list[tuple[str, str]] = []
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

    def create_meeting(
        self, token: str, group_id: int, date: datetime, idempotency_key: Optional[str] = None
    ) -> MeetingSummary:
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

    def compose_weekly_report(self, token: str, group_id: int, period_start, period_end) -> WeeklyReportResult:
        self._maybe_fail("compose_weekly_report")
        self.composed_reports.append((group_id, period_start, period_end))
        return WeeklyReportResult(report_text=self.report_text, evidence=list(self.report_evidence))

    def answer_report_question(self, token, group_id, question, evidence, period_start, period_end) -> str:
        self._maybe_fail("answer_report_question")
        self.report_questions.append((group_id, question, list(evidence)))
        return self.report_answer

    def transcript_chunks_in_window(self, token: str, group_id: int, since, until) -> list[TranscriptChunk]:
        self._maybe_fail("transcript_chunks_in_window")
        if not self.transcript_chunks:
            raise NotFoundError("no transcripts in window")
        return self.transcript_chunks

    def get_job(self, token: str, job_id: str) -> BackendJob:
        self._maybe_fail("get_job")
        return self.backend_jobs[job_id]

    def list_jobs(self, token: str, kind=None, meeting_id=None, limit: int = 1) -> list[BackendJob]:
        self._maybe_fail("list_jobs")
        return [
            j for j in self.backend_jobs.values()
            if (kind is None or j.kind == kind) and (meeting_id is None or j.meeting_id == meeting_id)
        ][:limit]

    def cancel_job(self, token: str, job_id: str) -> BackendJob:
        self._maybe_fail("cancel_job")
        self.cancelled_backend_jobs.append(job_id)
        return self.backend_jobs[job_id]

    def _announce_job(self, on_job) -> None:
        if on_job is None:
            return
        if self.cancel_queries:
            raise JobCancelledError("cancelled")
        job_id = f"backend-job-{len(self.announced_jobs) + 1}"
        self.announced_jobs.append(job_id)
        on_job(job_id)

    def query_source(self, token: str, group_id: int, source: str, question: str, since=None, on_job=None) -> QueryAnswer:
        self._maybe_fail(f"query_{source}")
        self._announce_job(on_job)
        if source in self.unlinked_sources:
            raise NotFoundError(f"no {source} source linked")
        self.queries.append((source, question))
        return QueryAnswer(answer=self.source_answers.get(source, f"{source} answer"), sources_used=[source])

    def query_unified(self, token: str, group_id: int, question: str, sources=None, since=None, on_job=None) -> QueryAnswer:
        self._maybe_fail("query_unified")
        self._announce_job(on_job)
        used = [s for s in (sources or []) if s not in self.unlinked_sources]
        if not used:
            raise NotFoundError("no sources linked")
        self.queries.append(("unified:" + ",".join(used), question))
        return QueryAnswer(
            answer=" ".join(self.source_answers.get(s, f"{s} answer") for s in used),
            sources_used=used,
            errors={s: "unavailable" for s in sources or [] if s in self.unlinked_sources},
        )
