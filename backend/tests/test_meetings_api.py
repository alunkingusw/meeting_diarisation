from datetime import date, datetime, timezone

from backend.auth import create_token_for_group_members
from backend.models import users_groups


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


def test_create_meeting_idempotency_key_returns_existing_meeting(
    client, make_user, make_group, auth_header_for
):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    headers = {**auth_header_for(owner.id), "Idempotency-Key": "DIAR-2026-0921-0001"}
    payload = {"date": "2026-09-21T10:00:00+00:00"}

    first = client.post(f"/groups/{group.id}/meetings/", json=payload, headers=headers)
    second = client.post(f"/groups/{group.id}/meetings/", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


def test_create_meeting_idempotency_key_cannot_cross_groups(
    client, make_user, make_group, auth_header_for
):
    owner = make_user(username="owner")
    first_group = make_group(name="Team A", owner=owner)
    second_group = make_group(name="Team B", owner=owner)
    key_headers = {**auth_header_for(owner.id), "Idempotency-Key": "DIAR-2026-0921-0002"}
    payload = {"date": "2026-09-21T10:00:00+00:00"}

    first = client.post(f"/groups/{first_group.id}/meetings/", json=payload, headers=key_headers)
    second = client.post(f"/groups/{second_group.id}/meetings/", json=payload, headers=key_headers)

    assert first.status_code == 200
    assert second.status_code == 409


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
    assert first_response.json()["user_id"] == owner.id
    assert first_response.json()["group_member_id"] is None
    assert second_response.status_code == 201
    assert second_response.json()["comment"] == "A second comment"


def test_transcript_free_meeting_supports_comments_and_returns_them(
    client, make_user, make_group, auth_header_for
):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    headers = auth_header_for(owner.id)

    created_meeting = client.post(
        f"/groups/{group.id}/meetings/",
        json={"date": datetime.now(timezone.utc).isoformat()},
        headers=headers,
    )
    meeting_id = created_meeting.json()["id"]
    comment_response = client.post(
        f"/groups/{group.id}/meetings/{meeting_id}/comments",
        json={"comment": "Decided to move the launch review to Friday."},
        headers=headers,
    )
    meeting_response = client.get(
        f"/groups/{group.id}/meetings/{meeting_id}", headers=headers
    )

    assert created_meeting.status_code == 200
    assert comment_response.status_code == 201
    assert meeting_response.status_code == 200
    assert meeting_response.json()["media_files"] == []
    assert [comment["comment"] for comment in meeting_response.json()["comments"]] == [
        "Decided to move the launch review to Friday."
    ]


def test_group_member_can_add_meeting_comment(
    client, db_session, make_user, make_group, make_meeting, auth_header_for
):
    owner = make_user(username="owner")
    member = make_user(username="member")
    group = make_group(name="Team A", owner=owner)
    db_session.execute(users_groups.insert().values(user_id=member.id, group_id=group.id, role="member"))
    db_session.commit()
    meeting = make_meeting(group)

    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/comments",
        json={"comment": "Member feedback"},
        headers=auth_header_for(member.id),
    )

    assert response.status_code == 201
    assert response.json()["comment"] == "Member feedback"


def test_attendee_email_token_can_comment_with_member_attribution_and_group_scope(
    client, make_group, make_member, make_meeting
):
    group = make_group(name="Team A")
    other_group = make_group(name="Team B")
    member = make_member(name="Carol", group=group)
    meeting = make_meeting(group)
    other_meeting = make_meeting(other_group)
    headers = {
        "Authorization": f"Bearer {create_token_for_group_members([member.id])}"
    }

    comment_response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/comments",
        json={"comment": "Feedback from a group attendee"},
        headers=headers,
    )
    denied_response = client.post(
        f"/groups/{other_group.id}/meetings/{other_meeting.id}/comments",
        json={"comment": "Cross-group attempt"},
        headers=headers,
    )

    assert comment_response.status_code == 201
    assert comment_response.json()["user_id"] is None
    assert comment_response.json()["group_member_id"] == member.id
    assert denied_response.status_code == 403


def test_attendee_email_token_can_create_meeting_only_in_associated_group(
    client, make_group, make_member
):
    group = make_group(name="Team A")
    other_group = make_group(name="Team B")
    member = make_member(name="Carol", group=group)
    headers = {
        "Authorization": f"Bearer {create_token_for_group_members([member.id])}"
    }

    allowed = client.post(
        f"/groups/{group.id}/meetings/",
        json={"date": datetime.now(timezone.utc).isoformat()},
        headers=headers,
    )
    denied = client.post(
        f"/groups/{other_group.id}/meetings/",
        json={"date": datetime.now(timezone.utc).isoformat()},
        headers=headers,
    )

    assert allowed.status_code == 200
    assert denied.status_code == 403


def test_group_member_token_is_not_accepted_by_user_only_routes(
    client, make_group, make_member
):
    group = make_group(name="Team A")
    member = make_member(name="Carol", group=group)
    headers = {
        "Authorization": f"Bearer {create_token_for_group_members([member.id])}"
    }

    response = client.delete(f"/groups/{group.id}", headers=headers)

    assert response.status_code == 401


def test_group_member_cannot_manage_meeting(
    client, db_session, make_user, make_group, make_meeting, auth_header_for
):
    owner = make_user(username="owner")
    member = make_user(username="member")
    group = make_group(name="Team A", owner=owner)
    db_session.execute(users_groups.insert().values(user_id=member.id, group_id=group.id, role="member"))
    db_session.commit()
    meeting = make_meeting(group)

    response = client.delete(
        f"/groups/{group.id}/meetings/{meeting.id}", headers=auth_header_for(member.id)
    )

    assert response.status_code == 403


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
