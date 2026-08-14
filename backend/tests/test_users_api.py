def test_create_user(client):
    response = client.post("/users/", json={"username": "alice"})
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_list_users_empty(client):
    response = client.get("/users/")
    assert response.status_code == 200
    assert response.json() == []


def test_get_user(client, make_user):
    user = make_user(username="alice")
    response = client.get(f"/users/{user.id}")
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_get_user_not_found(client):
    response = client.get("/users/999999")
    assert response.status_code == 404


def test_login_issues_token_for_existing_user(client, make_user):
    user = make_user(username="alice")
    response = client.post("/users/login", data={"username": str(user.id)})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_rejects_unknown_user(client):
    response = client.post("/users/login", data={"username": "999999"})
    assert response.status_code == 404


def test_login_rejects_non_numeric_username(client):
    response = client.post("/users/login", data={"username": "not-a-number"})
    assert response.status_code == 400


def test_update_user(client, make_user):
    user = make_user(username="alice")
    response = client.put(f"/users/{user.id}", json={"username": "alice2"})
    assert response.status_code == 200
    assert response.json()["username"] == "alice2"
    assert client.get(f"/users/{user.id}").json()["username"] == "alice2"


def test_delete_user(client, make_user):
    user = make_user(username="alice")
    response = client.delete(f"/users/{user.id}")
    assert response.status_code == 200
    assert client.get(f"/users/{user.id}").status_code == 404
