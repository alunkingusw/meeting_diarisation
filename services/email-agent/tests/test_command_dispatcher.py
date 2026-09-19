from app.llm.command_dispatcher import CommandGraphDispatcher


class FakeClient:
    def login_for_email(self, email: str):
        return f"token-for-{email}"

    def add_comment(self, token: str, group_id: int, meeting_id: int, comment: str):
        assert token == "token-for-alice@example.com"
        return {
            "id": 9,
            "meeting_id": meeting_id,
            "user_id": 12,
            "comment": comment,
            "created": "2026-09-19T12:00:00Z",
        }


def test_command_dispatcher_uses_graph_for_add_comment():
    dispatcher = CommandGraphDispatcher(FakeClient())

    result = dispatcher.execute_add_comment("alice@example.com", 7, 42, "Discuss the deadline.")

    assert result["result"]["comment"] == "Discuss the deadline."
    assert [event["event"] for event in result["audit_events"]] == [
        "login_start",
        "login_result",
        "add_comment_start",
        "add_comment_result",
    ]
