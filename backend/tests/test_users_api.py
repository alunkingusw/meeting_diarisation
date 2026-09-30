def test_create_user_requires_admin(client, make_user, auth_header_for):
    response = client.post("/users/", json={
        "username": "alice", "password": "correct-horse-battery-staple"
    })
    assert response.status_code == 401

    regular_user = make_user(username="regular")
    response = client.post(
        "/users/",
        json={"username": "alice", "password": "correct-horse-battery-staple"},
        headers=auth_header_for(regular_user.id),
    )
    assert response.status_code == 403

    admin = make_user(username="admin", is_admin=True)
    response = client.post(
        "/users/",
        json={"username": "alice", "password": "correct-horse-battery-staple"},
        headers=auth_header_for(admin.id),
    )
    assert response.status_code == 201
    assert response.json()["username"] == "alice"
    assert "password_hash" not in response.json()


def test_bootstrap_initial_admin_only_creates_first_user(db_session, monkeypatch):
    from backend.config import settings
    from backend.startup import bootstrap_initial_admin
    from backend.models import User
    from werkzeug.security import check_password_hash

    monkeypatch.setattr(settings, "initial_admin_username", "  install-admin  ")
    monkeypatch.setattr(settings, "initial_admin_password", "correct-horse-battery-staple")
    monkeypatch.setattr(settings, "initial_admin_email", "install@example.com")

    user_id = bootstrap_initial_admin()
    assert user_id is not None
    user = db_session.query(User).filter(User.id == user_id).one()
    assert user.username == "install-admin"
    assert user.email == "install@example.com"
    assert user.is_admin
    assert check_password_hash(user.password_hash, "correct-horse-battery-staple")

    assert bootstrap_initial_admin() is None
    assert db_session.query(User).count() == 1


def test_list_users_requires_admin(client, make_user, auth_header_for):
    response = client.get("/users/")
    assert response.status_code == 401

    user = make_user()
    response = client.get("/users/", headers=auth_header_for(user.id))
    assert response.status_code == 403

    admin = make_user(username="admin", is_admin=True)
    response = client.get("/users/", headers=auth_header_for(admin.id))
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert all("password_hash" not in item for item in response.json())


def test_get_user_requires_admin(client, make_user, auth_header_for):
    user = make_user(username="alice")
    response = client.get(f"/users/{user.id}")
    assert response.status_code == 401
    admin = make_user(username="admin", is_admin=True)
    response = client.get(f"/users/{user.id}", headers=auth_header_for(admin.id))
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_login_requires_valid_password(client, make_user):
    user = make_user(username="alice")
    response = client.post("/users/login", data={
        "username": "alice", "password": "correct-horse-battery-staple"
    })
    assert response.status_code == 200
    assert response.json()["access_token"]

    response = client.post("/users/login", data={"username": "alice", "password": "wrong"})
    assert response.status_code == 401

    response = client.post("/users/login", data={"username": str(user.id), "password": "wrong"})
    assert response.status_code == 401


def test_get_current_user(client, make_user, auth_header_for):
    user = make_user(username="alice")
    response = client.get("/users/me", headers=auth_header_for(user.id))
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_get_user_not_found(client, make_user, auth_header_for):
    admin = make_user(username="admin", is_admin=True)
    response = client.get("/users/999999", headers=auth_header_for(admin.id))
    assert response.status_code == 404


def test_update_user_requires_admin_and_can_reset_password(client, make_user, auth_header_for):
    user = make_user(username="alice")
    response = client.put(f"/users/{user.id}", json={"username": "alice2"})
    assert response.status_code == 401
    admin = make_user(username="admin", is_admin=True)
    response = client.put(
        f"/users/{user.id}",
        json={"username": "alice2", "password": "a-new-long-password"},
        headers=auth_header_for(admin.id),
    )
    assert response.status_code == 200
    assert response.json()["username"] == "alice2"
    response = client.post("/users/login", data={
        "username": "alice2", "password": "a-new-long-password"
    })
    assert response.status_code == 200


def test_delete_user_requires_admin(client, make_user, auth_header_for):
    user = make_user(username="alice")
    response = client.delete(f"/users/{user.id}")
    assert response.status_code == 401
    admin = make_user(username="admin", is_admin=True)
    response = client.delete(f"/users/{user.id}", headers=auth_header_for(admin.id))
    assert response.status_code == 200
    assert client.get(f"/users/{user.id}", headers=auth_header_for(admin.id)).status_code == 404
