def test_resolve_aliases_matches_exact_case_insensitive_name(
    client, make_user, make_group, make_member, auth_header_for
):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    member = make_member(name="Bob", group=group)
    headers = auth_header_for(owner.id)

    response = client.post(
        f"/groups/{group.id}/aliases/resolve",
        json={"names": ["bob", "BOB", "Someone Else"]},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["bob"] == member.id
    assert body["BOB"] == member.id
    assert body["Someone Else"] is None


def test_member_aliases_can_be_saved_and_resolved(
    client, make_user, make_group, make_member_via_api, auth_header_for
):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    member = make_member_via_api(group, owner.id, name="Bob")
    headers = auth_header_for(owner.id)

    update_response = client.put(
        f"/groups/{group.id}/members/{member['id']}",
        json={"name": "Bob", "aliases": [" Robert ", "ROBERT", "Bobby"]},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["aliases"] == ["Robert", "Bobby"]

    resolve_response = client.post(
        f"/groups/{group.id}/aliases/resolve",
        json={"names": ["robert", "BOBBY"]},
        headers=headers,
    )
    assert resolve_response.status_code == 200
    assert resolve_response.json() == {"robert": member["id"], "BOBBY": member["id"]}


def test_resolve_aliases_requires_group_membership(
    client, make_user, make_group, make_member, auth_header_for
):
    owner = make_user(username="owner")
    outsider = make_user(username="outsider")
    group = make_group(name="Team A", owner=owner)
    make_member(name="Bob", group=group)

    response = client.post(
        f"/groups/{group.id}/aliases/resolve",
        json={"names": ["Bob"]},
        headers=auth_header_for(outsider.id),
    )
    assert response.status_code == 403
