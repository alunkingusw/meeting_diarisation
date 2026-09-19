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
def test_search_transcripts(client):
    respx.post(f"{BASE_URL}/groups/1/transcripts/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "chunk_id": "c1",
                        "meeting_id": "42",
                        "meeting_title": "Sprint planning",
                        "meeting_date": "2026-08-11",
                        "speaker": "Alice",
                        "text": "Next week",
                        "start_ts": "00:00:01",
                        "end_ts": "00:00:03",
                    }
                ]
            },
        )
    )

    hits = client.search_transcripts("tok", 1, "Next week")

    assert len(hits) == 1
    assert hits[0].speaker == "Alice"
    assert hits[0].meeting_id == "42"


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
