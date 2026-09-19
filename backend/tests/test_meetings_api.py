from datetime import date, datetime, timezone


def test_create_and_list_meetings(client, make_user, make_group, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    headers = auth_header_for(owner.id)

    create_response = client.post(
        f"/groups/{group.id}/meetings/",
        json={"date": datetime.now(timezone.utc).isoformat()},
        headers=headers,
    )
    assert create_response.status_code == 200
    meeting_id = create_response.json()["id"]

    list_response = client.get(f"/groups/{group.id}/meetings/", headers=headers)
    assert list_response.status_code == 200
    assert [m["id"] for m in list_response.json()] == [meeting_id]


def test_list_meetings_supports_inclusive_date_range(
    client, make_user, make_group, make_meeting, auth_header_for
):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    make_meeting(group, datetime(2026, 9, 18, 23, 59, tzinfo=timezone.utc))
    included = make_meeting(group, datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc))
    make_meeting(group, datetime(2026, 9, 20, 0, 1, tzinfo=timezone.utc))

    response = client.get(
        f"/groups/{group.id}/meetings/",
        params={"from_date": "2026-09-19", "to_date": "2026-09-19"},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    assert [meeting["id"] for meeting in response.json()] == [included.id]

    invalid_response = client.get(
        f"/groups/{group.id}/meetings/",
        params={"from_date": "2026-09-20", "to_date": "2026-09-19"},
        headers=auth_header_for(owner.id),
    )
    assert invalid_response.status_code == 400


def test_get_meeting_not_found(client, make_user, make_group, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    response = client.get(f"/groups/{group.id}/meetings/999999", headers=auth_header_for(owner.id))
    assert response.status_code == 404


def test_add_meeting_comment_sanitises_html_and_allows_multiple_comments(
    client, make_user, make_group, make_meeting, auth_header_for
):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)
    headers = auth_header_for(owner.id)

    first_response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/comments",
        json={"comment": "<b>Useful</b> feedback"},
        headers=headers,
    )
    second_response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/comments",
        json={"comment": "A second comment"},
        headers=headers,
    )

    assert first_response.status_code == 201
    assert first_response.json()["comment"] == "Useful feedback"
    assert second_response.status_code == 201
    assert second_response.json()["comment"] == "A second comment"


def test_add_meeting_comment_rejects_empty_sanitised_text(
    client, make_user, make_group, make_meeting, auth_header_for
):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)

    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/comments",
        json={"comment": "<script></script>"},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 422


def test_add_guest_attendee(client, make_user, make_group, make_meeting, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)
    headers = auth_header_for(owner.id)

    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/attendees",
        json={"guest": 1, "name": "Guest Speaker"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Guest Speaker"

    meeting_detail = client.get(f"/groups/{group.id}/meetings/{meeting.id}", headers=headers).json()
    assert [a["name"] for a in meeting_detail["attendees"]] == ["Guest Speaker"]


def test_add_existing_member_attendee(client, make_user, make_group, make_member, make_meeting, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    member = make_member(name="Bob", group=group)
    meeting = make_meeting(group)
    headers = auth_header_for(owner.id)

    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/attendees",
        json={"member_id": member.id},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["id"] == member.id


def test_add_attendee_invalid_data(client, make_user, make_group, make_meeting, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)

    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/attendees",
        json={},
        headers=auth_header_for(owner.id),
    )
    assert response.status_code == 400


def test_remove_attendee(client, make_user, make_group, make_member, make_meeting, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    member = make_member(name="Bob", group=group)
    meeting = make_meeting(group)
    headers = auth_header_for(owner.id)

    client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/attendees",
        json={"member_id": member.id},
        headers=headers,
    )
    response = client.delete(
        f"/groups/{group.id}/meetings/{meeting.id}/attendees/{member.id}", headers=headers
    )
    assert response.status_code == 200


def test_transcribe_requires_uploaded_audio(client, make_user, make_group, make_meeting, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)

    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/transcribe", headers=auth_header_for(owner.id)
    )
    assert response.status_code == 400
