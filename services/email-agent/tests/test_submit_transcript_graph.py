from pathlib import Path

import pytest

from app.diarisation.client import GroupSummary
from app.llm.submit_transcript_graph import build_submit_transcript_graph


class FakeClient:
    def __init__(self, groups):
        self.groups = groups
        self.uploaded = []
        self.attendees = []

    def login_for_email(self, email: str):
        return f"token-for-{email}"

    def list_groups(self, token: str):
        assert token == "token-for-alice@example.com"
        return self.groups

    def create_meeting(self, token: str, group_id: int, date, idempotency_key=None):
        assert token == "token-for-alice@example.com"
        assert group_id == 7
        assert idempotency_key == "DIAR-2026-0921-0001"
        return type("Meeting", (), {"id": 42})()

    def upload_file(self, token: str, group_id: int, meeting_id: int, filename: str, content: bytes):
        self.uploaded.append((group_id, meeting_id, filename, content))
        return type("RawFile", (), {"id": 43})()

    def resolve_aliases(self, token: str, group_id: int, names: list[str]):
        return {name: 101 if name == "Alice" else None for name in names}

    def add_attendee(self, token: str, group_id: int, meeting_id: int, member_id: int):
        self.attendees.append((group_id, meeting_id, member_id))
        return type("Attendee", (), {"id": member_id})()


def _state(path: Path, group_hint=None):
    return {
        "job_id": "DIAR-2026-0921-0001",
        "sender_email": "alice@example.com",
        "attachment_path": str(path),
        "attachment_filename": path.name,
        "attachment_size_bytes": path.stat().st_size,
        "max_attachment_size_bytes": 10000,
        "group_hint": group_hint,
        "meeting_date": "2026-09-21T10:00:00+00:00",
        "speakers": ["Alice", "Bob"],
    }


def test_submit_graph_validates_logs_in_and_resolves_group(tmp_path: Path):
    path = tmp_path / "meeting.vtt"
    path.write_text(
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\n"
        "Alice: hello there\n\n"
        "00:00:02.000 --> 00:00:04.000\n"
        "Bob: goodbye\n",
        encoding="utf-8",
    )
    client = FakeClient([GroupSummary(id=7, name="Team A")])
    graph = build_submit_transcript_graph(client)

    result = graph.invoke(_state(path))

    assert result["group_id"] == 7
    assert result["group_name"] == "Team A"
    assert result.get("clarification_question") is None
    assert result["meeting_id"] == 42
    assert result["raw_file_id"] == 43
    assert result["resolved_attendees"] == ["Alice"]
    assert result["unresolved_speakers"] == ["Bob"]
    assert client.uploaded == [(7, 42, "meeting.vtt", path.read_bytes())]
    assert client.attendees == [(7, 42, 101)]
    assert [event["event"] for event in result["audit_events"]] == [
        "validate_trusted_state",
        "meeting_date_present",
        "login_start",
        "login_result",
        "groups_listed",
        "group_matched",
        "create_meeting_start",
        "create_meeting_result",
        "transcript_uploaded",
        "attendees_resolved",
        "attendees_added",
    ]


def test_submit_graph_stops_with_clarification_for_ambiguous_group(tmp_path: Path):
    path = tmp_path / "meeting.vtt"
    path.write_text(
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\n"
        "Alice: hello there\n",
        encoding="utf-8",
    )
    graph = build_submit_transcript_graph(
        FakeClient([GroupSummary(id=7, name="Team A"), GroupSummary(id=8, name="Team B")])
    )

    result = graph.invoke(_state(path))

    assert result["group_id"] is None
    assert result["meeting_id"] is None
    assert "Which group" in result["clarification_question"]
    assert result["audit_events"][-1]["event"] == "clarification_required"


def test_submit_graph_asks_for_date_clarification_before_backend_login(tmp_path: Path):
    path = tmp_path / "meeting.vtt"
    path.write_text(
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\n"
        "Alice: hello there\n",
        encoding="utf-8",
    )

    class NoLoginClient(FakeClient):
        def login_for_email(self, email: str):
            raise AssertionError("login should not be attempted before the date is resolved")

    graph = build_submit_transcript_graph(NoLoginClient([GroupSummary(id=7, name="Team A")]))

    result = graph.invoke(_state(path) | {"meeting_date": None})

    assert result["meeting_id"] is None
    assert result["group_id"] is None
    assert "meeting date" in result["clarification_question"].lower()
    assert result["audit_events"][-1]["event"] == "clarification_required"


def test_submit_graph_rejects_non_vtt_before_backend_call(tmp_path: Path):
    path = tmp_path / "meeting.txt"
    path.write_text("not a transcript", encoding="utf-8")
    graph = build_submit_transcript_graph(FakeClient([]))

    with pytest.raises(ValueError, match=r"\.vtt"):
        graph.invoke(_state(path))
