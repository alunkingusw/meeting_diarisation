import pytest

from backend.models import users_groups


def test_upload_requires_auth(client, make_user, make_group, make_meeting):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)

    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/upload/",
        files={"file": ("audio.wav", b"fake audio bytes", "audio/wav")},
    )
    assert response.status_code == 401


def test_upload_audio_file(client, make_user, make_group, make_meeting, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)

    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/upload/",
        files={"file": ("audio.wav", b"fake audio bytes", "audio/wav")},
        headers=auth_header_for(owner.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["human_name"] == "audio.wav"
    assert body["type"] == "audio"


def test_upload_transcript_file(client, make_user, make_group, make_meeting, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)

    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/upload/",
        files={"file": ("transcript.vtt", b"WEBVTT", "text/vtt")},
        headers=auth_header_for(owner.id),
    )
    assert response.status_code == 200
    assert response.json()["type"] == "transcript_provided"


def test_group_member_can_upload_transcript_but_not_audio(
    client, db_session, make_user, make_group, make_meeting, auth_header_for
):
    owner = make_user(username="owner")
    member = make_user(username="member")
    group = make_group(name="Team A", owner=owner)
    db_session.execute(users_groups.insert().values(user_id=member.id, group_id=group.id, role="member"))
    db_session.commit()
    meeting = make_meeting(group)
    headers = auth_header_for(member.id)

    transcript_response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/upload/",
        files={"file": ("transcript.vtt", b"WEBVTT", "text/vtt")},
        headers=headers,
    )
    audio_response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/upload/",
        files={"file": ("audio.wav", b"fake audio bytes", "audio/wav")},
        headers=headers,
    )

    assert transcript_response.status_code == 200
    assert audio_response.status_code == 403


def test_upload_srt_converts_to_vtt(client, make_user, make_group, make_meeting, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)

    srt = b"1\n00:00:01,000 --> 00:00:02,000\nSpeaker 1: Hello\n"
    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/upload/",
        files={"file": ("transcript.srt", srt, "application/x-subrip")},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "transcript_provided"
    assert body["file_name"].endswith(".vtt")

    converted_response = client.get(
        f"/files/media/{group.id}/{meeting.id}/{body['file_name']}",
        headers=auth_header_for(owner.id),
    )
    assert converted_response.status_code == 200
    assert converted_response.content.startswith(b"WEBVTT")
    assert b"Speaker 1: Hello" in converted_response.content


@pytest.mark.parametrize("filename", ["transcript.txt", "transcript.json"])
def test_upload_rejects_removed_transcript_formats(
    client, make_user, make_group, make_meeting, auth_header_for, filename
):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)

    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/upload/",
        files={"file": (filename, b"transcript", "text/plain")},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 400


def test_upload_rejects_unsupported_extension(client, make_user, make_group, make_meeting, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)

    response = client.post(
        f"/groups/{group.id}/meetings/{meeting.id}/upload/",
        files={"file": ("malware.exe", b"binary", "application/octet-stream")},
        headers=auth_header_for(owner.id),
    )
    assert response.status_code == 400


def test_serve_media_not_found(client, make_user, make_group, make_meeting, auth_header_for):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)

    response = client.get(
        f"/files/media/{group.id}/{meeting.id}/does-not-exist.wav",
        headers=auth_header_for(owner.id),
    )
    assert response.status_code == 404


def test_serve_media_forbidden_for_non_member(client, make_user, make_group, make_meeting, auth_header_for):
    owner = make_user(username="owner")
    outsider = make_user(username="outsider")
    group = make_group(name="Team A", owner=owner)
    meeting = make_meeting(group)

    response = client.get(
        f"/files/media/{group.id}/{meeting.id}/does-not-exist.wav",
        headers=auth_header_for(outsider.id),
    )
    assert response.status_code == 403
