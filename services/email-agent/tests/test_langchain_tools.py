from app.diarisation.client import GroupSummary, GroupDetail, MemberSummary
from app.llm.manager_tools import build_manager_tools


class FakeManagerClient:
    def list_groups(self, token: str):
        assert token == "abc"
        return [GroupSummary(id=1, name="Team A")]

    def get_group(self, token: str, group_id: int):
        assert token == "abc"
        assert group_id == 1
        return GroupDetail(id=1, name="Team A", members=[MemberSummary(id=5, name="Alice")])

    def list_meetings(self, token: str, group_id: int, from_date=None, to_date=None):
        assert token == "abc"
        assert group_id == 1
        return []

    def get_meeting(self, token: str, group_id: int, meeting_id: int):
        return {"id": meeting_id, "group_id": group_id, "date": "2026-09-19T00:00:00"}

    def add_comment(self, token: str, group_id: int, meeting_id: int, comment: str):
        return {"id": 9, "meeting_id": meeting_id, "user_id": 12, "comment": comment, "created": "2026-09-19T12:00:00Z"}

    def resolve_aliases(self, token: str, group_id: int, names, source="transcript_name"):
        return {"Alice": 5}

    def search_transcripts(self, token: str, group_id: int, query: str, meeting_id=None):
        return [{"chunk_id": "c1", "meeting_id": "42", "speaker": "Alice", "text": query}]

    def login_for_email(self, email: str):
        return f"token-for-{email}"


def test_build_manager_tools_exposes_expected_calls():
    tools = {tool.name: tool for tool in build_manager_tools(FakeManagerClient())}

    assert set(tools) >= {
        "list_groups",
        "get_group",
        "list_meetings",
        "get_meeting",
        "add_comment",
        "resolve_aliases",
        "search_transcripts",
        "login_for_email",
    }

    assert tools["list_groups"].invoke({"token": "abc"}) == [{"id": 1, "name": "Team A"}]
    assert tools["get_group"].invoke({"token": "abc", "group_id": 1}) == {
        "id": 1,
        "name": "Team A",
        "members": [{"id": 5, "name": "Alice"}],
    }
    assert tools["login_for_email"].invoke({"email": "alice@example.com"}) == "token-for-alice@example.com"
