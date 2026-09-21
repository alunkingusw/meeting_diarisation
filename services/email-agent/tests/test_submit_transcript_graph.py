from pathlib import Path

import pytest

from app.diarisation.client import GroupSummary
from app.llm.submit_transcript_graph import build_submit_transcript_graph


class FakeClient:
    def __init__(self, groups):
        self.groups = groups

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
    }


def test_submit_graph_validates_logs_in_and_resolves_group(tmp_path: Path):
    path = tmp_path / "meeting.vtt"
    path.write_text("WEBVTT\n", encoding="utf-8")
    graph = build_submit_transcript_graph(FakeClient([GroupSummary(id=7, name="Team A")]))

    result = graph.invoke(_state(path))

    assert result["group_id"] == 7
    assert result["group_name"] == "Team A"
    assert result.get("clarification_question") is None
    assert result["meeting_id"] == 42
    assert [event["event"] for event in result["audit_events"]] == [
        "validate_trusted_state",
        "login_start",
        "login_result",
        "groups_listed",
        "group_matched",
        "create_meeting_start",
        "create_meeting_result",
    ]


def test_submit_graph_stops_with_clarification_for_ambiguous_group(tmp_path: Path):
    path = tmp_path / "meeting.vtt"
    path.write_text("WEBVTT\n", encoding="utf-8")
    graph = build_submit_transcript_graph(
        FakeClient([GroupSummary(id=7, name="Team A"), GroupSummary(id=8, name="Team B")])
    )

    result = graph.invoke(_state(path))

    assert result["group_id"] is None
    assert result["meeting_id"] is None
    assert "Which group" in result["clarification_question"]
    assert result["audit_events"][-1]["event"] == "clarification_required"


def test_submit_graph_rejects_non_vtt_before_backend_call(tmp_path: Path):
    path = tmp_path / "meeting.txt"
    path.write_text("not a transcript", encoding="utf-8")
    graph = build_submit_transcript_graph(FakeClient([]))

    with pytest.raises(ValueError, match=r"\.vtt"):
        graph.invoke(_state(path))
