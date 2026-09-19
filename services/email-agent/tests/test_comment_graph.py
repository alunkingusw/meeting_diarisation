from app.llm.comment_graph import build_add_comment_graph


class FakeClient:
    def login_for_email(self, email: str):
        return f"token-for-{email}"

    def add_comment(self, token: str, group_id: int, meeting_id: int, comment: str):
        assert token == "token-for-alice@example.com"
        assert group_id == 7
        assert meeting_id == 42
        return {"id": 9, "meeting_id": meeting_id, "user_id": 12, "comment": comment, "created": "2026-09-19T12:00:00Z"}


def test_add_comment_graph_executes_expected_steps():
    graph = build_add_comment_graph(FakeClient())

    result = graph.invoke({
        "sender_email": "alice@example.com",
        "group_id": 7,
        "meeting_id": 42,
        "comment": "Discuss the deadline.",
    })

    assert result["result"]["id"] == 9
    assert [event["event"] for event in result["audit_events"]] == [
        "login_start",
        "login_result",
        "add_comment_start",
        "add_comment_result",
    ]
