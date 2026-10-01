from jose import jwt


def test_service_user_token_resolves_email(client, make_user, db_session):
    user = make_user(username="alice")
    user.email = "Alice@Example.com"
    db_session.commit()

    response = client.post(
        "/admin/user-token",
        json={"email": " alice@example.com "},
        headers={"X-Service-Key": "test-service-key"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_service_user_token_falls_back_to_group_member(client, make_member, make_group, db_session):
    group = make_group(name="Team A")
    member = make_member(name="Carol", group=group)
    member.email = "carol@example.com"
    db_session.commit()

    response = client.post(
        "/admin/user-token",
        json={"email": "carol@example.com"},
        headers={"X-Service-Key": "test-service-key"},
    )

    assert response.status_code == 200
    payload = jwt.get_unverified_claims(response.json()["access_token"])
    assert payload["principal_type"] == "group_member"
    assert payload["group_member_ids"] == [member.id]


def test_user_token_takes_precedence_when_email_is_also_a_group_member(
    client, make_user, make_member, make_group, db_session
):
    user = make_user(username="carol")
    user.email = "carol@example.com"
    group = make_group(name="Team A")
    member = make_member(name="Carol", group=group)
    member.email = user.email
    db_session.commit()

    response = client.post(
        "/admin/user-token",
        json={"email": user.email},
        headers={"X-Service-Key": "test-service-key"},
    )

    payload = jwt.get_unverified_claims(response.json()["access_token"])
    assert response.status_code == 200
    assert payload.get("principal_type") != "group_member"
    assert payload["sub"] == str(user.id)


def test_service_user_token_uses_exact_email_matching(client, make_user, db_session):
    user = make_user(username="alice")
    user.email = "alice@example.com"
    db_session.commit()

    response = client.post(
        "/admin/user-token",
        json={"email": "ali%@example.com"},
        headers={"X-Service-Key": "test-service-key"},
    )

    assert response.status_code == 404


def test_group_member_email_map_contains_associated_members(
    client, make_member, make_group, db_session
):
    group = make_group(name="Team A")
    member = make_member(name="Carol", group=group)
    member.email = "Carol@Example.com"
    db_session.commit()

    response = client.get("/admin/group-members", headers={"X-Service-Key": "test-service-key"})

    assert response.status_code == 200
    assert response.json() == {"carol@example.com": [member.id]}


def test_service_user_token_rejects_invalid_service_key(client, make_user, db_session):
    user = make_user(username="alice")
    user.email = "alice@example.com"
    db_session.commit()

    response = client.post(
        "/admin/user-token",
        json={"email": "alice@example.com"},
        headers={"X-Service-Key": "wrong-key"},
    )

    assert response.status_code == 401