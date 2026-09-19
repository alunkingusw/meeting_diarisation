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