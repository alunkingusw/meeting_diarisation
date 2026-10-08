from datetime import date, datetime


def test_weekly_batch_persists_one_report_and_sends_only_to_group_owners(
    db_session, make_user, make_group, monkeypatch
):
    from backend.engine.report_schemas import WeeklyReportResponse
    from backend.jobs.handlers import weekly_reports
    from backend.models import WeeklyReport, users_groups

    owner = make_user(username="supervisor")
    owner.email = "Supervisor@example.com"
    group = make_group(name="Team A", owner=owner)
    group.project_expiry = date(2026, 10, 5)
    member = make_user(username="student")
    member.email = "student@example.com"
    db_session.execute(
        users_groups.insert().values(user_id=member.id, group_id=group.id, role="member")
    )
    expired_owner = make_user(username="expired-supervisor")
    expired_owner.email = "expired@example.com"
    expired_group = make_group(name="Expired team", owner=expired_owner)
    expired_group.project_expiry = date(2026, 10, 4)
    db_session.commit()

    sent = []
    monkeypatch.setattr(
        "backend.engine.report_graph.compose_weekly_report",
        lambda db, group, start, end: WeeklyReportResponse(
            group_id=group.id,
            group_name=group.name,
            period_start=start,
            period_end=end,
            report_text="A cited weekly update.",
            model="fake-model",
            evidence=[],
        ),
    )
    monkeypatch.setattr(
        "backend.email_client.send_email",
        lambda to, subject, body, job_id=None: sent.append((to, subject, body, job_id)),
    )

    class Context:
        def check_cancelled(self):
            pass

        def progress(self, message):
            pass

    result = weekly_reports(
        Context(),
        {"period_start": "2026-09-28", "period_end": "2026-10-05"},
    )

    report_id = f"WEEKLY-2026-09-28-{group.id:04d}"
    report = db_session.get(WeeklyReport, report_id)
    assert result == {"queued_groups": 1, "failed_groups": []}
    assert sent == [(
        "supervisor@example.com",
        f"Weekly project update - {report_id}",
        "Project: Team A\nPeriod: 2026-09-28 to 2026-10-05\n\n"
        "A cited weekly update.\n\nReply to this email with a question about this update.",
        report_id,
    )]
    assert report.status == "queued"
    assert report.recipients == ["supervisor@example.com"]
    assert report.queued_recipients == ["supervisor@example.com"]
    assert report.evidence == []
    assert db_session.query(WeeklyReport).filter_by(group_id=expired_group.id).count() == 0


def test_group_nudger_only_queues_for_opted_in_groups_without_meetings_and_deduplicates(
    db_session, make_user, make_group, make_member, make_meeting, monkeypatch
):
    from backend.jobs.handlers import group_nudger
    from backend.models import GroupNudge

    eligible_owner = make_user(username="eligible-owner")
    eligible_owner.email = "eligible-owner@example.com"
    eligible = make_group(name="Eligible", owner=eligible_owner)
    eligible.notify = True
    eligible.project_expiry = date(2026, 10, 8)
    recipient = make_member(name="Member", group=eligible)
    recipient.email = "member@example.com"

    active_owner = make_user(username="active-owner")
    active_owner.email = "active-owner@example.com"
    active = make_group(name="Already met", owner=active_owner)
    active.notify = True
    active_member = make_member(name="Active member", group=active)
    active_member.email = "active-member@example.com"
    make_meeting(active, datetime(2026, 10, 3, 12))

    opted_out_owner = make_user(username="opted-out-owner")
    opted_out_owner.email = "opted-out-owner@example.com"
    opted_out = make_group(name="Opted out", owner=opted_out_owner)
    opted_out_member = make_member(name="Opted out member", group=opted_out)
    opted_out_member.email = "opted-out-member@example.com"

    expired_owner = make_user(username="expired-owner")
    expired_owner.email = "expired-owner@example.com"
    expired = make_group(name="Expired", owner=expired_owner)
    expired.notify = True
    expired.project_expiry = date(2026, 10, 7)
    expired_member = make_member(name="Expired member", group=expired)
    expired_member.email = "expired-member@example.com"
    db_session.commit()

    sent = []
    monkeypatch.setattr(
        "backend.email_client.send_email",
        lambda **kwargs: sent.append(kwargs),
    )

    class Context:
        def check_cancelled(self):
            pass

    params = {"period_start": "2026-10-01", "period_end": "2026-10-08"}
    first = group_nudger(Context(), params)
    second = group_nudger(Context(), params)

    nudges = db_session.query(GroupNudge).all()
    assert first == {"nudged_groups": 1, "queued_recipients": 1, "failed_recipients": []}
    assert second == {"nudged_groups": 0, "queued_recipients": 0, "failed_recipients": []}
    assert len(sent) == 1
    assert sent[0]["to"] == "member@example.com"
    assert "no meeting is recorded for Eligible" in sent[0]["body"]
    assert "send the transcript or email the meeting details" in sent[0]["body"]
    assert len(nudges) == 1 and nudges[0].status == "queued"
