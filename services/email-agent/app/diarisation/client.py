"""Thin, deterministic wrapper over the real backend's REST API.

One method per endpoint the email interface actually needs - never a generic "call any
endpoint" interface, mirroring the same "explicit finite operations" principle used for the
LLM's command schema (spec S17). See
D:\\Documents\\Documents\\VS Projects\\group_meeting_transcripts\\backend\\routes for the
endpoints these wrap. There are deliberately no get_status/cancel_job methods - those backend
endpoints don't exist.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Optional

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.reports.models import ReportEvidence


class DiarisationApiError(Exception):
    """Base class for all errors raised by DiarisationClient."""


class AuthError(DiarisationApiError):
    """401/403 - the JWT was rejected or expired. Not retried."""


class NotFoundError(DiarisationApiError):
    """404 - the group/meeting/member referenced doesn't exist. Not retried."""


class ConflictError(DiarisationApiError):
    """409 - e.g. an alias already registered. Not retried."""


class ClientError(DiarisationApiError):
    """Any other 4xx - malformed request. Not retried."""


class TransientError(DiarisationApiError):
    """Timeouts and 5xx - retried internally with backoff."""


class JobFailedError(DiarisationApiError):
    """A backend job ended in the failed state. Not retried: re-submitting would redo the work."""


class JobCancelledError(DiarisationApiError):
    """The backend job was cancelled."""


@dataclass
class GroupSummary:
    id: int
    name: str


@dataclass
class MemberSummary:
    id: int
    name: str


@dataclass
class GroupDetail:
    id: int
    name: str
    members: list[MemberSummary] = field(default_factory=list)


@dataclass
class MeetingSummary:
    id: int
    group_id: int
    date: str


@dataclass
class RawFileSummary:
    id: int
    file_name: str
    human_name: str
    type: str


@dataclass
class AttendeeSummary:
    id: int
    name: str


@dataclass
class MeetingComment:
    id: int
    meeting_id: int
    user_id: int | None
    comment: str
    created: str
    group_member_id: int | None = None


@dataclass
class TranscriptChunk:
    chunk_id: str
    meeting_id: str
    meeting_title: str
    meeting_date: str
    speaker: str
    text: str
    start_ts: str
    end_ts: str

    def citation(self) -> str:
        return f"[{self.meeting_title}, {self.meeting_date}, {self.start_ts}-{self.end_ts}, {self.speaker}]"


@dataclass
class WeeklyReportResult:
    report_text: str
    evidence: list[ReportEvidence]
    unavailable: list[str] = field(default_factory=list)


@dataclass
class BackendJob:
    id: str
    kind: str
    state: str
    progress: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    meeting_id: Optional[int] = None

    @property
    def finished(self) -> bool:
        return self.state in ("completed", "failed", "cancelled")


@dataclass
class QueryAnswer:
    answer: str
    sources_used: list[str]
    # Per-source failures the backend tolerated because another source still answered.
    errors: dict[str, str] = field(default_factory=dict)


class DiarisationClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        max_retry_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
        service_api_key: Optional[str] = None,
        query_timeout: float = 180.0,
        job_poll_seconds: float = 2.0,
    ):
        self._query_timeout = query_timeout
        self._job_poll_seconds = job_poll_seconds
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self._retryer = Retrying(
            reraise=True,
            retry=retry_if_exception_type(TransientError),
            stop=stop_after_attempt(max_retry_attempts),
            wait=wait_exponential(multiplier=retry_backoff_seconds, min=retry_backoff_seconds),
        )
        self._service_api_key = service_api_key
        from app.diarisation.generated_adapter import GeneratedDiarisationAdapter

        self._generated = GeneratedDiarisationAdapter(base_url, timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "DiarisationClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --- endpoint methods -------------------------------------------------

    def login(self, user_id: int) -> str:
        """POST /users/login - trades a backend user_id for a JWT."""
        resp = self._request("POST", "/users/login", data={"username": str(user_id)})
        return resp.json()["access_token"]

    def login_for_email(self, email: str) -> str:
        """POST /admin/user-token using the trusted service key for a verified sender."""
        if not self._service_api_key:
            raise AuthError("DIARISATION_SERVICE_API_KEY is not configured")
        return self._retryer(
            self._generated.login_for_email,
            email,
            self._service_api_key,
        )

    def list_groups(self, token: str) -> list[GroupSummary]:
        """GET /groups/ - only the groups the JWT's user belongs to."""
        groups = self._retryer(self._generated.list_groups, token)
        return [GroupSummary(id=g["id"], name=g["name"]) for g in groups]

    def get_group(self, token: str, group_id: int) -> GroupDetail:
        """GET /groups/{id}"""
        data = self._retryer(self._generated.get_group, token, group_id)
        return GroupDetail(
            id=data.id,
            name=data.name,
            members=[MemberSummary(id=m.id, name=m.name) for m in data.members],
        )

    def create_meeting(
        self,
        token: str,
        group_id: int,
        date: datetime,
        idempotency_key: Optional[str] = None,
    ) -> MeetingSummary:
        """POST /groups/{id}/meetings/"""
        data = self._retryer(
            self._generated.create_meeting,
            token,
            group_id,
            date,
            idempotency_key,
        )
        return MeetingSummary(id=data["id"], group_id=data["group_id"], date=data["date"])

    def list_meetings(
        self,
        token: str,
        group_id: int,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> list[MeetingSummary]:
        """GET /groups/{id}/meetings/ with optional date range filters."""
        meetings = self._retryer(self._generated.list_meetings, token, group_id, from_date, to_date)
        return [
            MeetingSummary(id=m["id"], group_id=m["group_id"], date=m["date"]) for m in meetings
        ]

    def get_meeting(self, token: str, group_id: int, meeting_id: int) -> MeetingSummary:
        """GET /groups/{id}/meetings/{meeting_id}"""
        data = self._retryer(self._generated.get_meeting, token, group_id, meeting_id)
        return MeetingSummary(id=data["id"], group_id=data["group_id"], date=data["date"])

    def upload_file(
        self, token: str, group_id: int, meeting_id: int, filename: str, content: bytes
    ) -> RawFileSummary:
        """POST /groups/{id}/meetings/{id}/upload/ - multipart file upload."""
        data = self._retryer(
            self._generated.upload_file,
            token,
            group_id,
            meeting_id,
            filename,
            content,
        )
        return RawFileSummary(
            id=data["id"],
            file_name=data["file_name"],
            human_name=data["human_name"],
            type=data["type"],
        )

    def add_attendee(
        self, token: str, group_id: int, meeting_id: int, member_id: int
    ) -> AttendeeSummary:
        """POST /groups/{id}/meetings/{id}/attendees"""
        data = self._retryer(self._generated.add_attendee, token, group_id, meeting_id, member_id)
        return AttendeeSummary(id=data["id"], name=data["name"])

    def add_comment(
        self, token: str, group_id: int, meeting_id: int, comment: str
    ) -> MeetingComment:
        """POST /groups/{group_id}/meetings/{meeting_id}/comments"""
        return self._retryer(
            self._generated.add_comment,
            token,
            group_id,
            meeting_id,
            comment,
        )

    def resolve_aliases(
        self,
        token: str,
        group_id: int,
        names: list[str],
        source: Optional[str] = "transcript_name",
    ) -> dict[str, Optional[int]]:
        """POST /groups/{id}/aliases/resolve - VTT speaker labels -> known member_id (or null)."""
        data = self._retryer(self._generated.resolve_aliases, token, group_id, names, source)
        return {k: (None if v is None else int(v)) for k, v in data.items()}

    def search_transcripts(
        self, token: str, group_id: int, query: str, meeting_id: Optional[int] = None
    ) -> list[TranscriptChunk]:
        """POST /groups/{id}/conversation/query (retrieve_only) - semantic search over this group's
        submitted meetings, returning chunks with no LLM answer."""
        body = _query_body(query, None)
        body["retrieve_only"] = True
        if meeting_id is not None:
            body["meeting_id"] = meeting_id
        try:
            return self._transcript_chunks(token, group_id, body)
        except NotFoundError:
            return []

    def query_source(
        self,
        token: str,
        group_id: int,
        source: str,
        question: str,
        since: Optional[date] = None,
        on_job: Optional[Callable[[str], None]] = None,
    ) -> QueryAnswer:
        """POST /groups/{id}/{conversation|github|trello}/query - an answer from one source.

        With `on_job` the query runs as a backend job (so it can be cancelled and inspected); the
        callback receives the job id as soon as it exists, and this call waits for the result."""
        data = self._query(token, f"/groups/{group_id}/{source}/query", _query_body(question, since), on_job)
        return QueryAnswer(answer=data["answer"], sources_used=[source])

    def query_unified(
        self,
        token: str,
        group_id: int,
        question: str,
        sources: Optional[list[str]] = None,
        since: Optional[date] = None,
        on_job: Optional[Callable[[str], None]] = None,
    ) -> QueryAnswer:
        """POST /groups/{id}/query - the backend routes the question and merges source answers."""
        body = _query_body(question, since)
        if sources is not None:
            body["sources"] = sources
        data = self._query(token, f"/groups/{group_id}/query", body, on_job)
        return QueryAnswer(
            answer=data["answer"], sources_used=data["sources_used"], errors=data.get("errors", {})
        )

    def _query(self, token: str, path: str, body: dict, on_job: Optional[Callable[[str], None]]) -> dict:
        if on_job is None:
            return self._request(
                "POST", path, headers=_auth(token), json=body, timeout=self._query_timeout
            ).json()
        resp = self._request("POST", f"{path}?async=true", headers=_auth(token), json=body)
        job_id = resp.json()["job_id"]
        on_job(job_id)
        job = self._wait_for_job(token, job_id)
        return job.result or {}

    def _wait_for_job(self, token: str, job_id: str) -> BackendJob:
        deadline = time.monotonic() + self._query_timeout
        while True:
            job = self.get_job(token, job_id)
            if job.state == "completed":
                return job
            if job.state == "cancelled":
                raise JobCancelledError(f"Backend job {job_id} was cancelled")
            if job.state == "failed":
                # The backend reports "nothing to answer from" as a ValueError, as the sync API does with a 404.
                if job.error_type == "ValueError":
                    raise NotFoundError(job.error or "No matching data")
                raise JobFailedError(job.error or "Backend job failed")
            if time.monotonic() >= deadline:
                raise TransientError(f"Timed out waiting for backend job {job_id}")
            time.sleep(self._job_poll_seconds)

    def get_job(self, token: str, job_id: str) -> BackendJob:
        """GET /jobs/{id}"""
        return _job_from_api(self._request("GET", f"/jobs/{job_id}", headers=_auth(token)).json())

    def list_jobs(
        self, token: str, kind: Optional[str] = None, meeting_id: Optional[int] = None, limit: int = 1
    ) -> list[BackendJob]:
        """GET /jobs/ - newest first."""
        params: dict = {"limit": limit}
        if kind is not None:
            params["kind"] = kind
        if meeting_id is not None:
            params["meeting_id"] = meeting_id
        resp = self._request("GET", "/jobs/", headers=_auth(token), params=params)
        return [_job_from_api(item) for item in resp.json()]

    def cancel_job(self, token: str, job_id: str) -> BackendJob:
        """POST /jobs/{id}/cancel - ConflictError if the job already finished."""
        return _job_from_api(self._request("POST", f"/jobs/{job_id}/cancel", headers=_auth(token)).json())

    def transcript_chunks_in_window(
        self, token: str, group_id: int, since: date, until: date
    ) -> list[TranscriptChunk]:
        """POST /groups/{id}/conversation/query (retrieve_only) - the transcript chunks of meetings
        dated in [since, until), without an LLM answer. Raises NotFoundError if there are none."""
        body = _query_body("meetings and decisions in this period", since)
        body.update({"until": until.isoformat(), "retrieve_only": True})
        return self._transcript_chunks(token, group_id, body)

    def _transcript_chunks(self, token: str, group_id: int, body: dict) -> list[TranscriptChunk]:
        resp = self._request(
            "POST",
            f"/groups/{group_id}/conversation/query",
            headers=_auth(token),
            json=body,
            timeout=self._query_timeout,
        )
        return [
            TranscriptChunk(
                chunk_id=item["id"],
                meeting_id=str(item["metadata"].get("meeting_id", "")),
                meeting_title=item["metadata"].get("meeting_title", ""),
                meeting_date=item["metadata"].get("meeting_date", ""),
                speaker=item["metadata"].get("speaker", ""),
                text=item["text"],
                start_ts=item["metadata"].get("start_ts", ""),
                end_ts=item["metadata"].get("end_ts", ""),
            )
            for item in resp.json()["evidence"]
        ]

    def compose_weekly_report(
        self, token: str, group_id: int, period_start: date, period_end: date
    ) -> WeeklyReportResult:
        """POST /groups/{id}/reports/weekly - the backend gathers cited evidence from meetings,
        GitHub and Trello and writes the report; nothing is stored or sent."""
        resp = self._request(
            "POST",
            f"/groups/{group_id}/reports/weekly",
            headers=_auth(token),
            json={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
            timeout=self._query_timeout,
        )
        data = resp.json()
        return WeeklyReportResult(
            report_text=data["report_text"],
            evidence=[_evidence_from_api(item) for item in data["evidence"]],
            unavailable=data.get("unavailable", []),
        )

    def answer_report_question(
        self,
        token: str,
        group_id: int,
        question: str,
        evidence: list[ReportEvidence],
        period_start: date,
        period_end: date,
    ) -> str:
        """POST /groups/{id}/reports/answer - answers from the saved evidence only."""
        resp = self._request(
            "POST",
            f"/groups/{group_id}/reports/answer",
            headers=_auth(token),
            json={
                "question": question,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "evidence": [
                    {
                        "source": e.source, "evidence_id": e.evidence_id, "title": e.title,
                        "event_date": e.event_date, "content": e.content, "citation": e.citation,
                    }
                    for e in evidence
                ],
            },
            timeout=self._query_timeout,
        )
        return resp.json()["answer"]

    # --- request plumbing --------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        return self._retryer(self._do_request, method, path, **kwargs)

    def _do_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as e:
            raise TransientError(f"Timeout calling {method} {path}: {e}") from e
        except httpx.TransportError as e:
            raise TransientError(f"Transport error calling {method} {path}: {e}") from e

        if resp.status_code >= 500:
            raise TransientError(f"{method} {path} returned {resp.status_code}: {resp.text[:200]}")
        if resp.status_code in (401, 403):
            raise AuthError(f"{method} {path} returned {resp.status_code}: {resp.text[:200]}")
        if resp.status_code == 404:
            raise NotFoundError(f"{method} {path} returned 404: {resp.text[:200]}")
        if resp.status_code == 409:
            raise ConflictError(f"{method} {path} returned 409: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise ClientError(f"{method} {path} returned {resp.status_code}: {resp.text[:200]}")
        return resp


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _query_body(question: str, since: Optional[date]) -> dict:
    body: dict = {"question": question}
    if since is not None:
        body["since"] = since.isoformat()
    return body


def _evidence_from_api(item: dict) -> ReportEvidence:
    return ReportEvidence(
        source=item["source"],
        evidence_id=item["evidence_id"],
        title=item["title"],
        event_date=item.get("event_date"),
        content=item["content"],
        citation=item["citation"],
        raw_json=json.dumps(item, sort_keys=True),
    )


def _job_from_api(item: dict) -> BackendJob:
    return BackendJob(
        id=item["id"], kind=item["kind"], state=item["state"], progress=item.get("progress"),
        result=item.get("result"), error=item.get("error"), error_type=item.get("error_type"),
        meeting_id=item.get("meeting_id"),
    )
