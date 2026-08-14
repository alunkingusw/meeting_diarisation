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
