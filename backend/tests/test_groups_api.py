def test_create_group_requires_auth(client):
    response = client.post("/groups/", json={"name": "Team A"})
    assert response.status_code == 401


def test_create_and_list_group(client, make_user, auth_header_for):
    user = make_user()
    headers = auth_header_for(user.id)

    create_response = client.post("/groups/", json={"name": "Team A"}, headers=headers)
    assert create_response.status_code == 200
    assert create_response.json()["name"] == "Team A"

    list_response = client.get("/groups/", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


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
        json={"name": "Team B"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Team B"
    assert client.get(f"/groups/{group.id}", headers=headers).json()["name"] == "Team B"


def test_delete_group(client, make_user, make_group, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    headers = auth_header_for(owner.id)

    response = client.delete(f"/groups/{group.id}", headers=headers)
    assert response.status_code == 200
    assert client.get(f"/groups/{group.id}", headers=headers).status_code == 404
