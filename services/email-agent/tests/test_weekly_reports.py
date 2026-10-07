from datetime import date, datetime, timezone
from pathlib import Path

from app.jobs.store import Outbox
from app.mail.fake_client import make_test_email
from app.reports.models import ReportEvidence
from app.reports.reply import WeeklyReportReplyService
from app.reports.store import ReportStore
from app.settings import Settings
from app.weekly_update import reporting_period
from app.admin.notifier import AdminNotifier
from app.diarisation.client import GroupSummary
from app.reports.workflow import WeeklyReportWorkflow
from tests.fakes import FakeDiarisationClient


def test_report_identity_is_idempotent_and_evidence_is_persisted(db_path: Path):
    store = ReportStore(db_path)
    first = store.create_or_get(7, "Team A", "alice@uni.ac.uk", 12, "2026-09-07", "2026-09-14")
    second = store.create_or_get(7, "Team A", "alice@uni.ac.uk", 12, "2026-09-07", "2026-09-14")

    assert first.report_id == second.report_id == "WEEKLY-2026-09-07-0007"

    store.replace_evidence(
        first.report_id,
        [ReportEvidence("github", "issue-12", "Issue 12", "2026-09-10", "API work", "repo#12", "{}")],
    )
    assert store.evidence(first.report_id)[0].citation == "repo#12"


def test_weekly_report_reply_uses_persisted_message_link(db_path: Path):
    reports = ReportStore(db_path)
    report = reports.create_or_get(7, "Team A", "alice@uni.ac.uk", 12, "2026-09-07", "2026-09-14")
    reports.replace_evidence(
        report.report_id,
        [ReportEvidence("meetings", "m1", "Planning", "2026-09-10", "We agreed to ship.", "[Planning]", "{}")],
    )
    outbox = Outbox(db_path)
    original_outbox_id = outbox.enqueue(
        "alice@uni.ac.uk", f"Weekly project update - {report.report_id}", "Report", job_id=report.report_id
    )
    outbox.mark_sent(original_outbox_id, "<weekly-report@mail>")

    msg = make_test_email(
        "alice@uni.ac.uk",
        subject=f"Re: Weekly project update - {report.report_id}",
        body_text="What was agreed?",
        in_reply_to="<weekly-report@mail>",
        references="<weekly-report@mail>",
    )
    diarisation = FakeDiarisationClient(groups=[GroupSummary(id=7, name="Team A")])
    WeeklyReportReplyService(reports, outbox, diarisation).reply(msg, report.report_id)

    pending = outbox.pending()
    assert len(pending) == 1
    assert pending[0].job_id == report.report_id
    assert pending[0].in_reply_to_message_id == msg.message_id
    assert pending[0].references == "<weekly-report@mail> " + msg.message_id
    assert pending[0].body_text == "The team agreed to ship. [Planning]"
    group_id, question, evidence = diarisation.report_questions[0]
    assert (group_id, question) == (7, "What was agreed?")
    assert evidence[0].citation == "[Planning]"


def test_reporting_period_uses_configured_lookback_and_timezone():
    settings = Settings.model_validate({"weekly_update": {"lookback_days": 7}})
    start, end = reporting_period(settings, datetime(2026, 9, 14, 8, tzinfo=timezone.utc))
    assert start == date(2026, 9, 7)
    assert end == date(2026, 9, 14)


def test_weekly_workflow_persists_backend_report_and_queues_email(db_path: Path):
    reports = ReportStore(db_path)
    outbox = Outbox(db_path)
    report = reports.create_or_get(7, "Team A", "alice@uni.ac.uk", 12, "2026-09-07", "2026-09-14")
    diarisation = FakeDiarisationClient(groups=[GroupSummary(id=7, name="Team A")])
    diarisation.report_evidence = [
        ReportEvidence("meetings", "meeting-1-summary", "Meeting", "2026-09-08", "Agreed.", "Meeting 1", "{}")
    ]
    admin = AdminNotifier(db_path, outbox, admin_email=None)

    WeeklyReportWorkflow(reports, outbox, diarisation, admin).run(report.report_id)

    assert diarisation.composed_reports == [(7, date(2026, 9, 7), date(2026, 9, 14))]
    assert reports.get(report.report_id).status == "QUEUED"
    assert reports.evidence(report.report_id)[0].evidence_id == "meeting-1-summary"
    queued = outbox.pending()[0]
    assert queued.job_id == report.report_id
    assert "The team agreed to ship. [Planning]" in queued.body_text


def test_weekly_workflow_failure_marks_report_failed(db_path: Path):
    reports = ReportStore(db_path)
    outbox = Outbox(db_path)
    report = reports.create_or_get(7, "Team A", "alice@uni.ac.uk", 12, "2026-09-07", "2026-09-14")
    diarisation = FakeDiarisationClient(
        groups=[GroupSummary(id=7, name="Team A")], fail_on="compose_weekly_report"
    )
    admin = AdminNotifier(db_path, outbox, admin_email=None)

    WeeklyReportWorkflow(reports, outbox, diarisation, admin).run(report.report_id)

    assert reports.get(report.report_id).status == "FAILED"
    assert outbox.pending() == []
