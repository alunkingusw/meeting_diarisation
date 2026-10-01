def test_create_and_list_members(client, make_user, make_group, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    headers = auth_header_for(owner.id)

    create_response = client.post(f"/groups/{group.id}/members/", json={"name": "Bob"}, headers=headers)
    assert create_response.status_code == 200
    assert create_response.json()["name"] == "Bob"

    list_response = client.get(f"/groups/{group.id}/members/", headers=headers)
    assert list_response.status_code == 200
    members = list_response.json()
    assert len(members) == 1
    assert members[0]["name"] == "Bob"


def test_create_member_welcome_email_uses_owner_contact(
    client, db_session, make_user, make_group, auth_header_for, monkeypatch
):
    import backend.routes.group_members as group_members_route

    owner = make_user(username="owner")
    owner.email = "owner@example.com"
    db_session.commit()
    group = make_group(name="Team A", owner=owner)
    sent_emails = []
    monkeypatch.setattr(
        group_members_route, "send_email", lambda **kwargs: sent_emails.append(kwargs)
    )

    response = client.post(
        f"/groups/{group.id}/members/",
        json={"name": "Bob", "email": "bob@example.com"},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    assert len(sent_emails) == 1
    assert "owner@example.com" in sent_emails[0]["body"]


def test_list_members_forbidden_for_non_member(client, make_user, make_group, make_member, auth_header_for):
    owner = make_user(username="owner")
    outsider = make_user(username="outsider")
    group = make_group(name="Team A", owner=owner)
    make_member(name="Bob", group=group)

    response = client.get(f"/groups/{group.id}/members/", headers=auth_header_for(outsider.id))
    assert response.status_code == 403


def test_get_member_not_found(client, make_user, make_group, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)

    response = client.get(f"/groups/{group.id}/members/999999", headers=auth_header_for(owner.id))
    assert response.status_code == 404


def test_update_member(client, make_user, make_group, make_member_via_api, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    member = make_member_via_api(group, owner.id, name="Bob")
    headers = auth_header_for(owner.id)

    response = client.put(
        f"/groups/{group.id}/members/{member['id']}", json={"name": "Bobby"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Bobby"


def test_delete_member(client, make_user, make_group, make_member, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    member = make_member(name="Bob", group=group)
    headers = auth_header_for(owner.id)

    response = client.delete(f"/groups/{group.id}/members/{member.id}", headers=headers)
    assert response.status_code == 200
    assert client.get(f"/groups/{group.id}/members/{member.id}", headers=headers).status_code == 404


def test_upload_member_embedding_rejects_bad_extension(client, make_user, make_group, make_member, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    member = make_member(name="Bob", group=group)
    headers = auth_header_for(owner.id)

    response = client.post(
        f"/groups/{group.id}/members/{member.id}/embedding",
        files={"file": ("sample.txt", b"not audio", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 400
