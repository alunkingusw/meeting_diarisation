from backend.auth import create_token_for_group_members


def test_create_group_requires_auth(client):
    response = client.post("/groups/", json={"name": "Team A"})
    assert response.status_code == 401


def test_create_and_list_group(client, make_user, auth_header_for):
    user = make_user()
    headers = auth_header_for(user.id)

    create_response = client.post(
        "/groups/",
        json={"name": "Team A", "project_expiry": "2027-06-30"},
        headers=headers,
    )
    assert create_response.status_code == 200
    assert create_response.json()["name"] == "Team A"
    assert create_response.json()["project_expiry"] == "2027-06-30"

    list_response = client.get("/groups/", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_group_member_email_token_lists_only_associated_groups(client, make_group, make_member):
    group = make_group(name="Team A")
    make_group(name="Team B")
    member = make_member(name="Carol", group=group)
    headers = {
        "Authorization": f"Bearer {create_token_for_group_members([member.id])}"
    }

    response = client.get("/groups/", headers=headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [group.id]
    assert set(response.json()[0]) == {"id", "name"}


def test_get_group_forbidden_for_non_member(client, make_user, make_group, auth_header_for):
    owner = make_user(username="owner")
    outsider = make_user(username="outsider")
    group = make_group(name="Team A", owner=owner)

    response = client.get(f"/groups/{group.id}", headers=auth_header_for(outsider.id))
    assert response.status_code == 403


def test_get_group_allowed_for_member(client, make_user, make_group, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)

    response = client.get(f"/groups/{group.id}", headers=auth_header_for(owner.id))
    assert response.status_code == 200
    assert response.json()["name"] == "Team A"
    assert response.json()["github_connected"] is False
    assert response.json()["trello_connected"] is False


def test_get_group_reports_provider_access(client, db_session, make_user, make_group, auth_header_for, monkeypatch):
    import backend.integrations as integrations

    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    group.github_repo_url = "https://github.com/example/project"
    group.trello_board_id = "board-id"
    db_session.commit()

    monkeypatch.setattr(integrations.GitHubClient, "check_repo_access", lambda self, url: True)
    monkeypatch.setattr(integrations.TrelloClient, "check_board_access", lambda self, board_id: True)

    response = client.get(f"/groups/{group.id}", headers=auth_header_for(owner.id))

    assert response.status_code == 200
    assert response.json()["github_connected"] is True
    assert response.json()["trello_connected"] is True


def test_get_group_reports_denied_provider_access(client, db_session, make_user, make_group, auth_header_for, monkeypatch):
    import backend.integrations as integrations

    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    group.github_repo_url = "https://github.com/example/project"
    group.trello_board_id = "board-id"
    db_session.commit()

    monkeypatch.setattr(integrations.GitHubClient, "check_repo_access", lambda self, url: False)
    monkeypatch.setattr(integrations.TrelloClient, "check_board_access", lambda self, board_id: False)

    response = client.get(f"/groups/{group.id}", headers=auth_header_for(owner.id))

    assert response.status_code == 200
    assert response.json()["github_connected"] is False
    assert response.json()["trello_connected"] is False


def test_get_group_not_found(client, make_user, auth_header_for):
    user = make_user()
    response = client.get("/groups/999999", headers=auth_header_for(user.id))
    assert response.status_code == 404


def test_update_group(client, make_user, make_group, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    headers = auth_header_for(owner.id)

    response = client.put(
        f"/groups/{group.id}",
        params={"name": "Team B"},
        json={"name": "Team B", "project_expiry": "2027-06-30"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Team B"
    assert response.json()["project_expiry"] == "2027-06-30"
    details = client.get(f"/groups/{group.id}", headers=headers).json()
    assert details["name"] == "Team B"
    assert details["project_expiry"] == "2027-06-30"


def test_delete_group(client, make_user, make_group, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    headers = auth_header_for(owner.id)

    response = client.delete(f"/groups/{group.id}", headers=headers)
    assert response.status_code == 200
    assert client.get(f"/groups/{group.id}", headers=headers).status_code == 404
