from jose import jwt
from datetime import date
from types import SimpleNamespace


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


def test_service_user_token_falls_back_to_group_member(client, make_member, make_group, db_session):
    group = make_group(name="Team A")
    member = make_member(name="Carol", group=group)
    member.email = "carol@example.com"
    db_session.commit()

    response = client.post(
        "/admin/user-token",
        json={"email": "carol@example.com"},
        headers={"X-Service-Key": "test-service-key"},
    )

    assert response.status_code == 200
    payload = jwt.get_unverified_claims(response.json()["access_token"])
    assert payload["principal_type"] == "group_member"
    assert payload["group_member_ids"] == [member.id]


def test_user_token_takes_precedence_when_email_is_also_a_group_member(
    client, make_user, make_member, make_group, db_session
):
    user = make_user(username="carol")
    user.email = "carol@example.com"
    group = make_group(name="Team A")
    member = make_member(name="Carol", group=group)
    member.email = user.email
    db_session.commit()

    response = client.post(
        "/admin/user-token",
        json={"email": user.email},
        headers={"X-Service-Key": "test-service-key"},
    )

    payload = jwt.get_unverified_claims(response.json()["access_token"])
    assert response.status_code == 200
    assert payload.get("principal_type") != "group_member"
    assert payload["sub"] == str(user.id)


def test_service_user_token_uses_exact_email_matching(client, make_user, db_session):
    user = make_user(username="alice")
    user.email = "alice@example.com"
    db_session.commit()

    response = client.post(
        "/admin/user-token",
        json={"email": "ali%@example.com"},
        headers={"X-Service-Key": "test-service-key"},
    )

    assert response.status_code == 404


def test_group_member_email_map_contains_associated_members(
    client, make_member, make_group, db_session
):
    group = make_group(name="Team A")
    member = make_member(name="Carol", group=group)
    member.email = "Carol@Example.com"
    db_session.commit()

    response = client.get("/admin/group-members", headers={"X-Service-Key": "test-service-key"})

    assert response.status_code == 200
    assert response.json() == {"carol@example.com": [member.id]}


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


def test_weekly_report_batch_requires_service_key_and_queues_for_owner(
    client, make_user, make_group, db_session, monkeypatch
):
    owner = make_user(username="supervisor")
    owner.email = "supervisor@example.com"
    make_group(name="Team A", owner=owner)
    submitted = []

    def fake_submit(db, kind, params):
        submitted.append((kind, params))
        return SimpleNamespace(id="weekly-job", state="queued")

    monkeypatch.setattr("backend.routes.admin.submit_job", fake_submit)
    body = {"period_start": "2026-09-28", "period_end": "2026-10-05"}

    denied = client.post("/admin/weekly-reports/run", json=body)
    accepted = client.post(
        "/admin/weekly-reports/run", json=body, headers={"X-Service-Key": "test-service-key"}
    )

    assert denied.status_code == 401
    assert accepted.status_code == 202
    assert accepted.json() == {"job_id": "weekly-job", "state": "queued"}
    assert submitted == [
        ("weekly_reports", {"period_start": "2026-09-28", "period_end": "2026-10-05"})
    ]


def test_weekly_report_answer_is_limited_to_recorded_recipients(
    client, make_user, make_group, db_session, fake_llm
):
    from backend.models import WeeklyReport

    owner = make_user(username="supervisor")
    owner.email = "supervisor@example.com"
    group = make_group(name="Team A", owner=owner)
    report = WeeklyReport(
        report_id="WEEKLY-2026-09-28-0001",
        group_id=group.id,
        group_name=group.name,
        period_start=date(2026, 9, 28),
        period_end=date(2026, 10, 5),
        report_text="The team agreed to ship.",
        model="fake-model",
        evidence=[{
            "source": "meetings", "evidence_id": "m1", "title": "Planning",
            "content": "We agreed to ship.", "citation": "Planning",
        }],
        recipients=["supervisor@example.com"],
        queued_recipients=["supervisor@example.com"],
        status="queued",
    )
    db_session.add(report)
    db_session.commit()
    headers = {"X-Service-Key": "test-service-key"}

    denied = client.post(
        f"/admin/weekly-reports/{report.report_id}/answer",
        json={"sender_email": "other@example.com", "question": "What was agreed?"},
        headers=headers,
    )
    accepted = client.post(
        f"/admin/weekly-reports/{report.report_id}/answer",
        json={"sender_email": "SUPERVISOR@example.com", "question": "What was agreed?"},
        headers=headers,
    )

    assert denied.status_code == 404
    assert accepted.status_code == 200
    assert accepted.json()["answer"] == "fake answer"
    assert "We agreed to ship." in fake_llm.prompts[-1]