from app.diarisation.client import GroupSummary
from app.llm.manager_graph import build_manager_graph


class FakeManagerClient:
    def list_groups(self, token: str):
        return [GroupSummary(id=1, name="Team A")]

    def get_group(self, token: str, group_id: int):
        return {"id": group_id, "name": "Team A", "members": []}

    def list_meetings(self, token: str, group_id: int, from_date=None, to_date=None):
        return []

    def get_meeting(self, token: str, group_id: int, meeting_id: int):
        return {"id": meeting_id, "group_id": group_id, "date": "2026-09-19T00:00:00"}

    def add_comment(self, token: str, group_id: int, meeting_id: int, comment: str):
        return {"id": 9, "meeting_id": meeting_id, "user_id": 12, "comment": comment, "created": "2026-09-19T12:00:00Z"}

    def resolve_aliases(self, token: str, group_id: int, names, source="transcript_name"):
        return {"Alice": 5}

    def search_transcripts(self, token: str, group_id: int, query: str, meeting_id=None):
        return [{"chunk_id": "c1", "speaker": "Alice", "text": query}]

    def login_for_email(self, email: str):
        return f"token-for-{email}"


def test_manager_graph_executes_tool_call():
    graph = build_manager_graph(FakeManagerClient())

    result = graph.invoke({
        "tool_name": "list_groups",
        "token": "abc",
        "arguments": {"token": "abc"},
    })

    assert result["result"] == [{"id": 1, "name": "Team A"}]
    assert len(result["audit_events"]) == 2
    assert result["audit_events"][0]["event"] == "tool_start"
    assert result["audit_events"][1]["event"] == "tool_result"
