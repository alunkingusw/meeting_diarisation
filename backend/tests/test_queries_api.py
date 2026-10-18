import json
from datetime import datetime, timezone
from uuid import uuid4

# backend modules are imported inside functions: backend.config reads env at import time,
# and the `app` fixture sets that env after collection.


def _linked_group(db_session, make_user, make_group, trello=True, github=True):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    group.github_repo_url = "https://github.com/example/project" if github else None
    group.trello_board_id = "board-id" if trello else None
    db_session.commit()
    return owner, group


def _seed_index(db_session, group):
    from backend.project_rag import group_service
    from backend.project_rag.models import Commit, TrelloAction

    repo = group_service.get_or_create_repo(db_session, group)
    db_session.add(
        Commit(
            repo_id=repo.id, sha="a" * 40, author_name="Alice", author_email="a@example.com",
            committed_at=datetime(2026, 1, 5, tzinfo=timezone.utc), message="Add login",
            files_changed=1, additions=10, deletions=2, diff_text="",
        )
    )
    db_session.add(
        TrelloAction(
            repo_id=repo.id, trello_action_id="t1", action_type="commentCard", card_id="c1",
            card_name="Login", member_creator="Bob", text="Blocked on design",
            created_at=datetime(2026, 1, 6, tzinfo=timezone.utc),
        )
    )
    db_session.commit()
    return repo


def test_github_query_returns_answer_and_stats(
    client, db_session, make_user, make_group, auth_header_for, fake_llm
):
    owner, group = _linked_group(db_session, make_user, make_group)
    _seed_index(db_session, group)

    response = client.post(
        f"/groups/{group.id}/github/query",
        json={"question": "What did Alice do?"},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "github"
    assert body["answer"] == "fake answer"
    assert body["stats"]["total_commits"] == 1
    assert body["stats"]["total_trello_actions"] == 0


def test_trello_query_is_scoped_to_trello(
    client, db_session, make_user, make_group, auth_header_for, fake_llm
):
    owner, group = _linked_group(db_session, make_user, make_group)
    _seed_index(db_session, group)

    response = client.post(
        f"/groups/{group.id}/trello/query",
        json={"question": "What is blocked?"},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stats"]["total_trello_actions"] == 1
    assert body["stats"]["total_commits"] == 0


def test_project_query_until_is_exclusive_for_evidence_and_stats(
    client, db_session, make_user, make_group, auth_header_for, fake_llm
):
    from backend.project_rag import group_service
    from backend.project_rag.models import Commit, TrelloAction

    owner, group = _linked_group(db_session, make_user, make_group)
    repo = group_service.get_or_create_repo(db_session, group)
    db_session.add_all(
        [
            Commit(
                repo_id=repo.id,
                sha="s" * 40,
                author_name="September",
                author_email="sep@example.invalid",
                committed_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
                message="September release work",
                files_changed=1,
                additions=2,
                deletions=0,
                diff_text="",
            ),
            Commit(
                repo_id=repo.id,
                sha="o" * 40,
                author_name="October",
                author_email="oct@example.invalid",
                committed_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
                message="October follow-up",
                files_changed=1,
                additions=3,
                deletions=0,
                diff_text="",
            ),
            TrelloAction(
                repo_id=repo.id,
                trello_action_id="sep-action",
                action_type="commentCard",
                card_id="sep-card",
                card_name="September card",
                member_creator="September",
                text="September work",
                created_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
            ),
            TrelloAction(
                repo_id=repo.id,
                trello_action_id="oct-action",
                action_type="commentCard",
                card_id="oct-card",
                card_name="October card",
                member_creator="October",
                text="October work",
                created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    for source, expected_text, excluded_text, total_key in (
        ("github", "September release work", "October follow-up", "total_commits"),
        ("trello", "September work", "October work", "total_trello_actions"),
    ):
        response = client.post(
            f"/groups/{group.id}/{source}/query",
            json={
                "question": "Summarize September work",
                "since": "2026-09-01",
                "until": "2026-10-01",
            },
            headers=auth_header_for(owner.id),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["stats"][total_key] == 1
        assert any(expected_text in item["text"] for item in body["evidence"])
        assert all(excluded_text not in item["text"] for item in body["evidence"])
        agent_payload = json.loads(fake_llm.agent_tool_results[-1])
        assert agent_payload["complete_window"] is True
        assert any(expected_text in item["text"] for item in agent_payload["evidence"])
        assert "deterministic stats" in fake_llm.agent_prompts[-1]

    unified = client.post(
        f"/groups/{group.id}/query",
        json={
            "question": "Summarize September release work",
            "sources": ["github", "trello"],
            "since": "2026-09-01",
            "until": "2026-10-01",
        },
        headers=auth_header_for(owner.id),
    )

    assert unified.status_code == 200
    results = unified.json()["results"]
    assert results["github"]["stats"]["total_commits"] == 1
    assert results["trello"]["stats"]["total_trello_actions"] == 1
    assert all(
        "October" not in item["text"]
        for result in results.values()
        for item in result["evidence"]
    )


def test_query_on_unlinked_source_is_404(
    client, db_session, make_user, make_group, auth_header_for
):
    owner, group = _linked_group(db_session, make_user, make_group, trello=False)

    response = client.post(
        f"/groups/{group.id}/trello/query",
        json={"question": "What is blocked?"},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 404


def test_query_requires_group_membership(
    client, db_session, make_user, make_group, auth_header_for
):
    _, group = _linked_group(db_session, make_user, make_group)
    outsider = make_user(username="outsider")

    response = client.post(
        f"/groups/{group.id}/github/query",
        json={"question": "What did Alice do?"},
        headers=auth_header_for(outsider.id),
    )

    assert response.status_code == 403


def test_unified_query_merges_sources(
    client, db_session, make_user, make_group, auth_header_for, fake_llm
):
    from backend.project_rag import group_service
    from backend.models import QueryConversationTurn

    owner, group = _linked_group(db_session, make_user, make_group)
    _seed_index(db_session, group)

    response = client.post(
        f"/groups/{group.id}/query",
        json={
            "question": "Summarise progress",
            "sources": ["github", "trello"],
            "source_questions": {"github": "What did Alice commit?", "trello": "What remains blocked?"},
        },
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sources_used"] == ["github", "trello"]
    assert body["conversation_id"] is None
    assert set(body["results"]) == {"github", "trello"}
    assert body["errors"] == {}
    assert "GitHub findings:" in body["answer"]
    assert "Trello findings:" in body["answer"]
    assert any("What did Alice commit?" in prompt for prompt in fake_llm.agent_prompts)
    assert any("What remains blocked?" in prompt for prompt in fake_llm.agent_prompts)
    assert db_session.query(QueryConversationTurn).count() == 0


def test_unified_query_continues_conversation_with_fresh_scoped_retrieval(
    client, db_session, make_user, make_group, auth_header_for, monkeypatch
):
    from backend.engine import query_graph
    from backend.engine.query_agent_schemas import SpecialistQueryResult
    from backend.models import QueryConversationTurn

    owner, group = _linked_group(db_session, make_user, make_group, trello=False)
    calls = []

    def fake_github_specialist(session, context, request):
        calls.append((context.user_id, context.group_id, request))
        answer = "Issue 42 is open." if len(calls) == 1 else "Issue 42 is now closed."
        return SpecialistQueryResult(
            source="github",
            question=request.question,
            answer=answer,
            model="fake-model",
        )

    monkeypatch.setattr(query_graph, "run_github_specialist", fake_github_specialist)
    conversation_id = uuid4()

    first = client.post(
        f"/groups/{group.id}/query",
        json={
            "question": "Find Ada's issue.",
            "sources": ["github"],
            "source_questions": {"github": "Find Ada's issue."},
            "conversation_id": str(conversation_id),
        },
        headers=auth_header_for(owner.id),
    )
    assert first.status_code == 200
    assert first.json()["conversation_id"] == str(conversation_id)

    followup = client.post(
        f"/groups/{group.id}/query",
        json={
            "question": "Is it still open?",
            "sources": ["github"],
            "source_questions": {"github": "Is it still open?"},
            "conversation_id": str(conversation_id),
        },
        headers=auth_header_for(owner.id),
    )
    assert followup.status_code == 200
    assert followup.json()["answer"] == "GitHub findings:\nIssue 42 is now closed."
    assert len(calls) == 2
    assert calls[1][2].question == "Is it still open?"
    assert calls[1][2].retrieval_question == "Find Ada's issue.\nFollow-up: Is it still open?"
    assert "Issue 42 is open." in calls[1][2].context
    assert db_session.query(QueryConversationTurn).filter_by(
        conversation_id=str(conversation_id), user_id=owner.id, group_id=group.id
    ).count() == 2

    other_user = make_user(username="other-user")
    group.users.append(other_user)
    db_session.commit()
    isolated = client.post(
        f"/groups/{group.id}/query",
        json={
            "question": "What did we ask?",
            "sources": ["github"],
            "source_questions": {"github": "What did we ask?"},
            "conversation_id": str(conversation_id),
        },
        headers=auth_header_for(other_user.id),
    )
    assert isolated.status_code == 200
    assert calls[2][0] == other_user.id
    assert calls[2][2].context is None
    assert calls[2][2].retrieval_question is None
    assert db_session.query(QueryConversationTurn).filter_by(
        conversation_id=str(conversation_id), user_id=other_user.id, group_id=group.id
    ).count() == 1

    other_group = make_group(name="Team B", owner=owner)
    other_group.github_repo_url = "https://github.com/example/other"
    db_session.commit()
    other_group_response = client.post(
        f"/groups/{other_group.id}/query",
        json={
            "question": "What did we ask?",
            "sources": ["github"],
            "source_questions": {"github": "What did we ask?"},
            "conversation_id": str(conversation_id),
        },
        headers=auth_header_for(owner.id),
    )
    assert other_group_response.status_code == 200
    assert calls[3][0] == owner.id
    assert calls[3][1] == other_group.id
    assert calls[3][2].context is None
    assert calls[3][2].retrieval_question is None


def test_api_followup_requeries_mutable_github_state(
    client, db_session, make_user, make_group, auth_header_for, fake_llm
):
    from backend.project_rag import group_service
    from backend.project_rag.models import Issue

    owner, group = _linked_group(db_session, make_user, make_group, trello=False)
    repo = group_service.get_or_create_repo(db_session, group)
    issue = Issue(
        repo_id=repo.id,
        github_issue_number=42,
        title="Release gate",
        body="Track release approval.",
        author="Ada",
        state="open",
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    db_session.add(issue)
    db_session.commit()
    conversation_id = uuid4()
    headers = auth_header_for(owner.id)

    first = client.post(
        f"/groups/{group.id}/query",
        json={
            "question": "Is issue 42 open?",
            "sources": ["github"],
            "source_questions": {"github": "Is issue 42 open?"},
            "conversation_id": str(conversation_id),
        },
        headers=headers,
    )
    assert first.status_code == 200
    first_tool_result = json.loads(fake_llm.agent_tool_results[-1])
    assert first_tool_result["stats"]["open_issues"] == 1
    assert first_tool_result["stats"]["closed_issues"] == 0

    issue.state = "closed"
    db_session.commit()

    followup = client.post(
        f"/groups/{group.id}/query",
        json={
            "question": "Is it still open?",
            "sources": ["github"],
            "source_questions": {"github": "Is it still open?"},
            "conversation_id": str(conversation_id),
        },
        headers=headers,
    )
    assert followup.status_code == 200
    followup_tool_result = json.loads(fake_llm.agent_tool_results[-1])
    assert followup_tool_result["stats"]["open_issues"] == 0
    assert followup_tool_result["stats"]["closed_issues"] == 1
    assert "Prior turn context" in fake_llm.agent_prompts[-1]
    assert "fake answer" in fake_llm.agent_prompts[-1]
    assert "Is it still open?" in fake_llm.agent_prompts[-1]


def test_unified_query_reports_partial_failure(
    client, db_session, make_user, make_group, auth_header_for, fake_llm
):
    from backend.project_rag import group_service
    from backend.project_rag.models import TrelloAction

    owner, group = _linked_group(db_session, make_user, make_group)
    repo = group_service.get_or_create_repo(db_session, group)
    db_session.add(
        TrelloAction(
            repo_id=repo.id, trello_action_id="t1", action_type="commentCard", card_id="c1",
            card_name="Login", member_creator="Bob", text="Blocked on design",
            created_at=datetime(2026, 1, 6, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    response = client.post(
        f"/groups/{group.id}/query",
        json={"question": "Summarise progress", "sources": ["github", "trello"]},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sources_used"] == ["trello"]
    assert "github" in body["errors"]
    assert "Trello findings:" in body["answer"]
    assert "Unavailable sources:\n- github: unavailable" in body["answer"]


def test_unified_query_keeps_available_source_when_another_is_unlinked(
    client, db_session, make_user, make_group, auth_header_for, fake_llm
):
    owner, group = _linked_group(db_session, make_user, make_group, trello=False)
    _seed_index(db_session, group)

    response = client.post(
        f"/groups/{group.id}/query",
        json={"question": "Summarise progress", "sources": ["github", "trello"]},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sources_used"] == ["github"]
    assert "trello" in body["errors"]
    assert "Unavailable sources:\n- trello: unavailable" in body["answer"]


def test_unified_query_returns_service_unavailable_when_all_specialists_fail(
    client, db_session, make_user, make_group, auth_header_for, fake_llm
):
    from backend.llm.ollama_client import OllamaError

    owner, group = _linked_group(db_session, make_user, make_group)
    _seed_index(db_session, group)
    fake_llm.error = OllamaError("Ollama is unreachable")

    response = client.post(
        f"/groups/{group.id}/query",
        json={"question": "Summarise progress", "sources": ["github", "trello"]},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 503
    assert "Ollama is unreachable" in response.json()["detail"]


def test_ingest_requires_owner(client, db_session, make_user, make_group, auth_header_for):
    _, group = _linked_group(db_session, make_user, make_group)
    outsider = make_user(username="outsider")

    response = client.post(f"/groups/{group.id}/ingest", headers=auth_header_for(outsider.id))

    assert response.status_code == 403


def test_changing_repo_url_discards_github_index(db_session, make_user, make_group):
    from backend.project_rag import group_service
    from backend.project_rag.models import Commit, Repo, TrelloAction

    _, group = _linked_group(db_session, make_user, make_group)
    repo = _seed_index(db_session, group)

    group.github_repo_url = "https://github.com/example/other"
    db_session.commit()
    group_service.get_or_create_repo(db_session, group)

    assert db_session.query(Commit).filter(Commit.repo_id == repo.id).count() == 0
    assert db_session.query(TrelloAction).filter(TrelloAction.repo_id == repo.id).count() == 1
    assert db_session.get(Repo, repo.id).github_url == "https://github.com/example/other"


def test_group_rejects_non_github_repo_url(client, make_user, auth_header_for):
    owner = make_user(username="owner")

    response = client.post(
        "/groups/",
        json={"name": "Team", "github_repo_url": "file:///etc/passwd"},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 422


def test_stats_span_all_sources_and_use_group_name(
    client, db_session, make_user, make_group, auth_header_for
):
    owner, group = _linked_group(db_session, make_user, make_group)
    _seed_index(db_session, group)

    response = client.get(f"/groups/{group.id}/stats", headers=auth_header_for(owner.id))

    assert response.status_code == 200
    body = response.json()
    assert body["repo_name"] == "Team A"
    assert body["first_activity_at"].startswith("2026-01-05")
    assert body["last_activity_at"].startswith("2026-01-06")
