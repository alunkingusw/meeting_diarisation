from datetime import date

import httpx
import pytest
import respx

from app.diarisation.client import (
    AuthError,
    ClientError,
    ConflictError,
    DiarisationClient,
    NotFoundError,
    TransientError,
)

BASE_URL = "http://backend.test"


@pytest.fixture
def client():
    c = DiarisationClient(
        BASE_URL, timeout=1.0, max_retry_attempts=3, retry_backoff_seconds=0.01,
        service_api_key="service-secret",
    )
    yield c
    c.close()


@respx.mock
def test_login_returns_token(client):
    route = respx.post(f"{BASE_URL}/users/login").mock(
        return_value=httpx.Response(200, json={"access_token": "abc123", "token_type": "bearer"})
    )
    token = client.login(12)
    assert token == "abc123"
    assert route.calls.last.request.read() == b"username=12"


@respx.mock
def test_login_unknown_user_raises_not_found(client):
    respx.post(f"{BASE_URL}/users/login").mock(
        return_value=httpx.Response(404, json={"detail": "User not found"})
    )
    with pytest.raises(NotFoundError):
        client.login(999)


@respx.mock
def test_login_for_email_uses_service_key(client):
    route = respx.post(f"{BASE_URL}/admin/user-token").mock(
        return_value=httpx.Response(200, json={"access_token": "email-token", "token_type": "bearer"})
    )

    token = client.login_for_email("Alice@Example.com")

    assert token == "email-token"
    assert route.calls.last.request.headers["X-Service-Key"] == "service-secret"
    assert route.calls.last.request.read() == b'{"email":"Alice@Example.com"}'


@respx.mock
def test_weekly_report_operations_use_service_key(client):
    run_route = respx.post(f"{BASE_URL}/admin/weekly-reports/run").mock(
        return_value=httpx.Response(202, json={"job_id": "job-1", "state": "queued"})
    )
    answer_route = respx.post(
        f"{BASE_URL}/admin/weekly-reports/WEEKLY-2026-10-05-0007/answer"
    ).mock(return_value=httpx.Response(200, json={"answer": "The team agreed to ship."}))

    accepted = client.run_weekly_reports(date(2026, 10, 5), date(2026, 10, 12))
    answer = client.answer_scheduled_report(
        "WEEKLY-2026-10-05-0007", "alice@example.com", "What was agreed?"
    )

    assert accepted["job_id"] == "job-1"
    assert answer == "The team agreed to ship."
    assert run_route.calls.last.request.headers["X-Service-Key"] == "service-secret"
    assert answer_route.calls.last.request.headers["X-Service-Key"] == "service-secret"
    assert run_route.calls.last.request.read() == b'{"period_start":"2026-10-05","period_end":"2026-10-12"}'
    assert answer_route.calls.last.request.read() == b'{"sender_email":"alice@example.com","question":"What was agreed?"}'


@respx.mock
def test_list_groups(client):
    respx.get(f"{BASE_URL}/groups/").mock(
        return_value=httpx.Response(
            200, json=[{"id": 1, "name": "Team A"}, {"id": 2, "name": "Team B"}]
        )
    )
    groups = client.list_groups("tok")
    assert [g.name for g in groups] == ["Team A", "Team B"]


@respx.mock
def test_get_group_includes_members(client):
    respx.get(f"{BASE_URL}/groups/1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 1,
                "name": "Team A",
                "created": "2026-01-01T00:00:00",
                    "members": [
                        {
                            "id": 5,
                            "name": "Alice",
                            "created": "2026-01-01T00:00:00",
                            "embedding_audio_path": None,
                        }
                    ],
            },
        )
    )
    group = client.get_group("tok", 1)
    assert group.name == "Team A"
    assert group.members[0].name == "Alice"


@respx.mock
def test_list_meetings(client):
    respx.get(f"{BASE_URL}/groups/1/meetings/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 42, "group_id": 1, "date": "2026-08-11T00:00:00"},
                {"id": 43, "group_id": 1, "date": "2026-08-12T00:00:00"},
            ],
        )
    )

    meetings = client.list_meetings("tok", 1)

    assert [m.id for m in meetings] == [42, 43]
    assert [m.date for m in meetings] == ["2026-08-11T00:00:00", "2026-08-12T00:00:00"]


@respx.mock
def test_get_meeting(client):
    respx.get(f"{BASE_URL}/groups/1/meetings/42").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 42,
                "group_id": 1,
                "date": "2026-08-11T00:00:00",
                "created": "2026-08-10T09:00:00",
                "attendees": [],
                "media_files": [],
            },
        )
    )

    meeting = client.get_meeting("tok", 1, 42)

    assert meeting.id == 42
    assert meeting.group_id == 1
    assert meeting.date == "2026-08-11T00:00:00"


@respx.mock
def test_create_meeting(client):
    respx.post(f"{BASE_URL}/groups/1/meetings/").mock(
        return_value=httpx.Response(
            200, json={"id": 42, "group_id": 1, "date": "2026-08-11T00:00:00"}
        )
    )
    from datetime import datetime

    meeting = client.create_meeting("tok", 1, datetime(2026, 8, 11))
    assert meeting.id == 42
    assert meeting.group_id == 1


@respx.mock
def test_create_meeting_sends_idempotency_key(client):
    route = respx.post(f"{BASE_URL}/groups/1/meetings/").mock(
        return_value=httpx.Response(
            200, json={"id": 42, "group_id": 1, "date": "2026-08-11T00:00:00"}
        )
    )
    from datetime import datetime

    client.create_meeting("tok", 1, datetime(2026, 8, 11), idempotency_key="DIAR-2026-0921-0001")

    assert route.calls.last.request.headers["Idempotency-Key"] == "DIAR-2026-0921-0001"


@respx.mock
def test_upload_file(client):
    respx.post(f"{BASE_URL}/groups/1/meetings/42/upload/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 99,
                "file_name": "uuid_meeting.vtt",
                "human_name": "meeting.vtt",
                "type": "transcript_provided",
            },
        )
    )
    result = client.upload_file("tok", 1, 42, "meeting.vtt", b"WEBVTT\n\n1\n...")
    assert result.id == 99
    assert result.type == "transcript_provided"


@respx.mock
def test_upload_file_sends_real_multipart_file(client):
    route = respx.post(f"{BASE_URL}/groups/1/meetings/42/upload/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 99,
                "file_name": "uuid_meeting.vtt",
                "human_name": "meeting.vtt",
                "type": "transcript_provided",
            },
        )
    )

    client.upload_file("tok", 1, 42, "meeting.vtt", b"WEBVTT\n\n1\n...")

    request = route.calls.last.request
    body = request.content
    assert b'filename="meeting.vtt"' in body
    assert b"WEBVTT" in body


@respx.mock
def test_add_attendee(client):
    respx.post(f"{BASE_URL}/groups/1/meetings/42/attendees").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 5,
                "name": "Alice",
                "created": "2026-01-01T00:00:00",
                "embedding_audio_path": None,
            },
        )
    )
    attendee = client.add_attendee("tok", 1, 42, 5)
    assert attendee.name == "Alice"


@respx.mock
def test_resolve_aliases(client):
    respx.post(f"{BASE_URL}/groups/1/aliases/resolve").mock(
        return_value=httpx.Response(
            200,
            json={
                "Alice": 5,
                "Unknown Person": None,
            },
        )
    )
    resolved = client.resolve_aliases("tok", 1, ["Alice", "Unknown Person"])
    assert resolved == {"Alice": 5, "Unknown Person": None}


@respx.mock
def test_search_transcripts_uses_conversation_endpoint_retrieve_only(client):
    route = respx.post(f"{BASE_URL}/groups/1/conversation/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "answer": "",
                "evidence": [
                    {
                        "id": "c1",
                        "text": "Next week",
                        "metadata": {
                            "meeting_id": "42", "meeting_title": "Sprint planning",
                            "meeting_date": "2026-08-11", "speaker": "Alice",
                            "start_ts": "00:00:01", "end_ts": "00:00:03",
                        },
                    }
                ],
            },
        )
    )

    hits = client.search_transcripts("tok", 1, "Next week", meeting_id=42)

    assert len(hits) == 1 and hits[0].speaker == "Alice" and hits[0].meeting_id == "42"
    sent = route.calls.last.request.read()
    assert b'"retrieve_only":true' in sent and b'"meeting_id":42' in sent


@respx.mock
def test_search_transcripts_returns_empty_when_nothing_matches(client):
    respx.post(f"{BASE_URL}/groups/1/conversation/query").mock(
        return_value=httpx.Response(404, json={"detail": "No indexed meeting transcripts match this question"})
    )

    assert client.search_transcripts("tok", 1, "anything") == []


@respx.mock
def test_conflict_raises_conflict_error(client):
    respx.post(f"{BASE_URL}/groups/1/meetings/42/attendees").mock(
        return_value=httpx.Response(409, json={"detail": "already an attendee"})
    )
    with pytest.raises(ConflictError):
        client.add_attendee("tok", 1, 42, 5)


@respx.mock
def test_expired_token_raises_auth_error_and_is_not_retried(client):
    route = respx.get(f"{BASE_URL}/groups/").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid or expired token"})
    )
    with pytest.raises(AuthError):
        client.list_groups("expired-tok")
    assert route.call_count == 1  # AuthError must not be retried


@respx.mock
def test_add_comment_posts_to_group_meeting_comments_endpoint(client):
    route = respx.post(f"{BASE_URL}/groups/7/meetings/42/comments").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 9,
                "meeting_id": 42,
                "user_id": 12,
                "comment": "Discuss the deadline.",
                "created": "2026-09-19T12:00:00Z",
            },
        )
    )

    result = client.add_comment("tok", 7, 42, "Discuss the deadline.")

    assert result.id == 9
    assert result.meeting_id == 42
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"
    assert route.calls.last.request.read() == b'{"comment":"Discuss the deadline."}'


@respx.mock
def test_client_error_not_retried(client):
    route = respx.post(f"{BASE_URL}/groups/1/meetings/").mock(
        return_value=httpx.Response(400, json={"detail": "bad request"})
    )
    from datetime import datetime

    with pytest.raises(ClientError):
        client.create_meeting("tok", 1, datetime(2026, 8, 11))
    assert route.call_count == 1


@respx.mock
def test_transient_5xx_is_retried_and_eventually_succeeds(client):
    route = respx.get(f"{BASE_URL}/groups/")
    route.side_effect = [
        httpx.Response(503, json={"detail": "unavailable"}),
        httpx.Response(503, json={"detail": "unavailable"}),
        httpx.Response(200, json=[{"id": 1, "name": "Team A"}]),
    ]
    groups = client.list_groups("tok")
    assert [g.name for g in groups] == ["Team A"]
    assert route.call_count == 3


@respx.mock
def test_transient_error_exhausts_retries_and_raises(client):
    route = respx.get(f"{BASE_URL}/groups/").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )
    with pytest.raises(TransientError):
        client.list_groups("tok")
    assert route.call_count == 3  # max_retry_attempts


@respx.mock
def test_timeout_is_treated_as_transient(client):
    respx.get(f"{BASE_URL}/groups/").mock(side_effect=httpx.ConnectTimeout("boom"))
    with pytest.raises(TransientError):
        client.list_groups("tok")


@respx.mock
def test_query_source_posts_to_source_endpoint(client):
    route = respx.post(f"{BASE_URL}/groups/3/github/query").mock(
        return_value=httpx.Response(200, json={"answer": "Two open issues.", "source": "github"})
    )

    result = client.query_source("tok", 3, "github", "open issues?")

    assert result.answer == "Two open issues."
    assert result.sources_used == ["github"]
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"
    assert route.calls.last.request.read() == b'{"question":"open issues?"}'


@respx.mock
def test_query_unified_sends_sources_and_since(client):
    from datetime import date

    route = respx.post(f"{BASE_URL}/groups/3/query").mock(
        return_value=httpx.Response(
            200,
            json={"answer": "Merged.", "sources_used": ["github", "trello"], "errors": {"trello": "x"}},
        )
    )

    result = client.query_unified("tok", 3, "progress?", sources=["github", "trello"], since=date(2026, 9, 1))

    assert result.sources_used == ["github", "trello"]
    assert result.errors == {"trello": "x"}
    assert route.calls.last.request.read() == (
        b'{"question":"progress?","since":"2026-09-01","sources":["github","trello"]}'
    )


@respx.mock
def test_query_source_not_linked_raises_not_found(client):
    respx.post(f"{BASE_URL}/groups/3/trello/query").mock(
        return_value=httpx.Response(404, json={"detail": "This group has no trello source linked"})
    )
    with pytest.raises(NotFoundError):
        client.query_source("tok", 3, "trello", "blocked?")


@respx.mock
def test_compose_weekly_report_posts_period_and_maps_evidence(client):
    from datetime import date

    route = respx.post(f"{BASE_URL}/groups/3/reports/weekly").mock(
        return_value=httpx.Response(
            200,
            json={
                "report_text": "All good. [Meeting 1, 2026-09-08]",
                "unavailable": ["github (nothing ingested yet)"],
                "evidence": [{
                    "source": "meetings", "evidence_id": "meeting-1-summary", "title": "Meeting",
                    "event_date": "2026-09-08", "content": "Agreed.", "citation": "Meeting 1, 2026-09-08",
                }],
            },
        )
    )

    result = client.compose_weekly_report("tok", 3, date(2026, 9, 7), date(2026, 9, 14))

    assert result.report_text.startswith("All good")
    assert result.unavailable == ["github (nothing ingested yet)"]
    assert result.evidence[0].citation == "Meeting 1, 2026-09-08"
    assert route.calls.last.request.read() == b'{"period_start":"2026-09-07","period_end":"2026-09-14"}'


@respx.mock
def test_answer_report_question_sends_saved_evidence(client):
    from datetime import date

    from app.reports.models import ReportEvidence

    route = respx.post(f"{BASE_URL}/groups/3/reports/answer").mock(
        return_value=httpx.Response(200, json={"answer": "Ship it.", "model": "m"})
    )
    evidence = [ReportEvidence("meetings", "m1", "Planning", "2026-09-08", "Agreed.", "Planning", "{}")]

    answer = client.answer_report_question(
        "tok", 3, "What was agreed?", evidence, date(2026, 9, 7), date(2026, 9, 14)
    )

    assert answer == "Ship it."
    sent = route.calls.last.request.read()
    assert b'"question":"What was agreed?"' in sent and b'"evidence_id":"m1"' in sent


def _job_json(state, **extra):
    return {"id": "j1", "kind": "query", "state": state, "progress": None, "result": None, "error": None, **extra}


@respx.mock
def test_async_query_waits_for_the_job_and_reports_the_id(client):
    client._job_poll_seconds = 0
    respx.post(f"{BASE_URL}/groups/3/github/query", params={"async": "true"}).mock(
        return_value=httpx.Response(202, json={"job_id": "j1", "state": "queued"})
    )
    respx.get(f"{BASE_URL}/jobs/j1").mock(
        side_effect=[
            httpx.Response(200, json=_job_json("running")),
            httpx.Response(200, json=_job_json("completed", result={"answer": "Two issues.", "source": "github"})),
        ]
    )
    seen = []

    result = client.query_source("tok", 3, "github", "open issues?", on_job=seen.append)

    assert result.answer == "Two issues." and seen == ["j1"]


@respx.mock
def test_async_query_failure_modes_map_to_client_errors(client):
    from app.diarisation.client import JobCancelledError, JobFailedError

    client._job_poll_seconds = 0
    respx.post(f"{BASE_URL}/groups/3/trello/query", params={"async": "true"}).mock(
        return_value=httpx.Response(202, json={"job_id": "j1", "state": "queued"})
    )
    job = respx.get(f"{BASE_URL}/jobs/j1")

    job.mock(return_value=httpx.Response(200, json=_job_json("failed", error="nothing ingested", error_type="ValueError")))
    with pytest.raises(NotFoundError):
        client.query_source("tok", 3, "trello", "q", on_job=lambda _: None)

    job.mock(return_value=httpx.Response(200, json=_job_json("failed", error="Ollama down", error_type="OllamaError")))
    with pytest.raises(JobFailedError):
        client.query_source("tok", 3, "trello", "q", on_job=lambda _: None)

    job.mock(return_value=httpx.Response(200, json=_job_json("cancelled")))
    with pytest.raises(JobCancelledError):
        client.query_source("tok", 3, "trello", "q", on_job=lambda _: None)


@respx.mock
def test_list_and_cancel_jobs(client):
    respx.get(f"{BASE_URL}/jobs/").mock(
        return_value=httpx.Response(200, json=[_job_json("running", kind="transcript_processing", meeting_id=42)])
    )
    cancel_route = respx.post(f"{BASE_URL}/jobs/j1/cancel").mock(
        return_value=httpx.Response(200, json=_job_json("cancelled"))
    )

    jobs = client.list_jobs("tok", kind="transcript_processing", meeting_id=42)
    cancelled = client.cancel_job("tok", "j1")

    assert jobs[0].meeting_id == 42 and not jobs[0].finished
    assert cancelled.state == "cancelled" and cancel_route.called
