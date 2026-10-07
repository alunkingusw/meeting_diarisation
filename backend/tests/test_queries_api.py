from datetime import datetime, timezone

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

    owner, group = _linked_group(db_session, make_user, make_group)
    _seed_index(db_session, group)

    response = client.post(
        f"/groups/{group.id}/query",
        json={"question": "Summarise progress", "sources": ["github", "trello"]},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sources_used"] == ["github", "trello"]
    assert set(body["results"]) == {"github", "trello"}
    assert body["errors"] == {}


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
