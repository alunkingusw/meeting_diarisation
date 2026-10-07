from datetime import date


def test_weekly_batch_persists_one_report_and_sends_only_to_group_owners(
    db_session, make_user, make_group, monkeypatch
):
    from backend.engine.report_schemas import WeeklyReportResponse
    from backend.jobs.handlers import weekly_reports
    from backend.models import WeeklyReport, users_groups

    owner = make_user(username="supervisor")
    owner.email = "Supervisor@example.com"
    group = make_group(name="Team A", owner=owner)
    member = make_user(username="student")
    member.email = "student@example.com"
    db_session.execute(
        users_groups.insert().values(user_id=member.id, group_id=group.id, role="member")
    )
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
