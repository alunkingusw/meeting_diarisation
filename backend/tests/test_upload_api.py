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
