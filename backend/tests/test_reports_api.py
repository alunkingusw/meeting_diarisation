import pytest
from datetime import date, datetime


@pytest.fixture(autouse=True)
def _llm(fake_llm):
    return fake_llm


def _group(db_session, make_user, make_group, linked=False):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    if linked:
        group.github_repo_url = "https://github.com/example/project"
        db_session.commit()
    return owner, group


def test_weekly_report_uses_summaries_and_comments_in_window(
    client, db_session, make_user, make_group, make_meeting, auth_header_for, monkeypatch
):
    from backend.models import MeetingComment

    owner, group = _group(db_session, make_user, make_group)
    inside = make_meeting(group, datetime(2026, 9, 8, 10))
    inside.summary = "The team agreed to ship the API."
    db_session.add(MeetingComment(meeting_id=inside.id, user_id=owner.id, comment="Needs docs"))
    make_meeting(group, datetime(2026, 8, 1, 10)).summary = "Too early"
    db_session.commit()

    response = client.post(
        f"/groups/{group.id}/reports/weekly",
        json={"period_start": "2026-09-07", "period_end": "2026-09-14"},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["report_text"] == "fake answer"
    ids = [e["evidence_id"] for e in body["evidence"]]
    assert ids == [f"meeting-{inside.id}-summary", f"meeting-{inside.id}-comments"]
    assert body["evidence"][1]["content"].startswith("owner (")
    assert body["unavailable"] == []


def test_weekly_report_falls_back_to_transcript_chunks_for_unsummarised_meetings(
    client, db_session, make_user, make_group, make_meeting, auth_header_for, monkeypatch
):
    owner, group = _group(db_session, make_user, make_group)
    meeting = make_meeting(group, datetime(2026, 9, 8, 10))
    chunk = {
        "chunk_id": f"{meeting.id}_00000", "meeting_id": str(meeting.id), "meeting_title": "Team A",
        "meeting_date": "2026-09-08", "speaker": "Alice", "text": "We agreed to ship.",
        "start_ts": "00:00:01.000", "end_ts": "00:00:09.000",
    }
    other = {**chunk, "chunk_id": "99_00000", "meeting_id": "99"}
    monkeypatch.setattr(
        "backend.engine.report_graph.transcripts_in_window", lambda *a, **k: [chunk, other]
    )

    response = client.post(
        f"/groups/{group.id}/reports/weekly",
        json={"period_start": "2026-09-07", "period_end": "2026-09-14"},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    evidence = response.json()["evidence"]
    assert [e["evidence_id"] for e in evidence] == [f"{meeting.id}_00000"]
    assert evidence[0]["citation"] == "Team A, 2026-09-08, 00:00:01.000-00:00:09.000, Alice"


def test_weekly_report_marks_linked_but_empty_source_unavailable(
    client, db_session, make_user, make_group, auth_header_for, monkeypatch
):
    owner, group = _group(db_session, make_user, make_group, linked=True)

    response = client.post(
        f"/groups/{group.id}/reports/weekly",
        json={"period_start": "2026-09-07", "period_end": "2026-09-14"},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    assert response.json()["unavailable"] == ["github (nothing ingested yet)"]


def test_weekly_report_rejects_empty_period_and_non_members(
    client, db_session, make_user, make_group, auth_header_for
):
    owner, group = _group(db_session, make_user, make_group)
    outsider = make_user(username="outsider")
    body = {"period_start": "2026-09-14", "period_end": "2026-09-14"}

    assert client.post(
        f"/groups/{group.id}/reports/weekly", json=body, headers=auth_header_for(owner.id)
    ).status_code == 422
    assert client.post(
        f"/groups/{group.id}/reports/weekly",
        json={"period_start": "2026-09-07", "period_end": "2026-09-14"},
        headers=auth_header_for(outsider.id),
    ).status_code == 403


def test_report_answer_uses_supplied_evidence(
    client, db_session, make_user, make_group, auth_header_for, fake_llm
):
    owner, group = _group(db_session, make_user, make_group)

    response = client.post(
        f"/groups/{group.id}/reports/answer",
        json={
            "question": "What was agreed?", "period_start": "2026-09-07", "period_end": "2026-09-14",
            "evidence": [{
                "source": "meetings", "evidence_id": "m1", "title": "Planning",
                "content": "We agreed to ship.", "citation": "Planning",
            }],
        },
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "fake answer"
    assert "We agreed to ship." in fake_llm.prompts[0] and "[Planning]" in fake_llm.prompts[0]


def test_weekly_report_treats_quiet_ingested_source_as_no_evidence(
    client, db_session, make_user, make_group, auth_header_for, monkeypatch
):
    from datetime import datetime, timezone

    from backend.project_rag import group_service

    owner, group = _group(db_session, make_user, make_group, linked=True)
    repo = group_service.get_or_create_repo(db_session, group)
    repo.last_synced_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    db_session.commit()

    response = client.post(
        f"/groups/{group.id}/reports/weekly",
        json={"period_start": "2026-09-07", "period_end": "2026-09-14"},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    assert response.json()["unavailable"] == []
