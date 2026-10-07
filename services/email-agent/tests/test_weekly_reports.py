from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from app.jobs.store import Outbox
from app.mail.fake_client import make_test_email
from app.pipeline import WEEKLY_REPORT_ID_RE
from app.reports.reply import WeeklyReportReplyService
from app.settings import Settings
from app.weekly_update import reporting_period


def test_outbox_matches_weekly_report_by_sent_message_id(db_path: Path):
    outbox = Outbox(db_path)
    original_outbox_id = outbox.enqueue(
        "alice@uni.ac.uk", "Weekly project update - WEEKLY-2026-09-07-0007", "Report",
        job_id="WEEKLY-2026-09-07-0007",
    )
    outbox.mark_sent(original_outbox_id, "<weekly-report@mail>")

    assert outbox.get_weekly_report_id_by_message_id(
        "<weekly-report@mail>", "alice@uni.ac.uk"
    ) == "WEEKLY-2026-09-07-0007"
    assert outbox.get_weekly_report_id_by_message_id(
        "<weekly-report@mail>", "other@uni.ac.uk"
    ) is None


def test_report_id_matching_preserves_large_group_ids():
    report_id = "WEEKLY-2026-09-07-10000"
    assert WEEKLY_REPORT_ID_RE.findall(report_id) == [report_id]


def test_weekly_report_reply_uses_backend_and_preserves_thread(db_path: Path):
    outbox = Outbox(db_path)
    msg = make_test_email(
        "alice@uni.ac.uk",
        subject="Re: Weekly project update - WEEKLY-2026-09-07-0007",
        body_text="What was agreed?",
        in_reply_to="<weekly-report@mail>",
        references="<weekly-report@mail>",
    )
    diarisation = Mock()
    diarisation.answer_scheduled_report.return_value = "The team agreed to ship."
    report_id = "WEEKLY-2026-09-07-0007"
    WeeklyReportReplyService(outbox, diarisation).reply(msg, report_id, "alice@uni.ac.uk")

    pending = outbox.pending()
    assert len(pending) == 1
    assert pending[0].job_id == report_id
    assert pending[0].in_reply_to_message_id == msg.message_id
    assert pending[0].references == "<weekly-report@mail> " + msg.message_id
    assert pending[0].body_text == "The team agreed to ship."
    diarisation.answer_scheduled_report.assert_called_once_with(
        report_id, "alice@uni.ac.uk", "What was agreed?"
    )


def test_reporting_period_uses_configured_lookback_and_timezone():
    settings = Settings.model_validate({"weekly_update": {"lookback_days": 7}})
    start, end = reporting_period(settings, datetime(2026, 9, 14, 8, tzinfo=timezone.utc))
    assert start == date(2026, 9, 7)
    assert end == date(2026, 9, 14)


def test_weekly_update_triggers_backend_for_configured_period(monkeypatch):
    from app.weekly_update import run_once

    settings = Settings.model_validate({"weekly_update": {"lookback_days": 7}})
    calls = []

    class Backend:
        def __init__(self, *args):
            pass

        def run_weekly_reports(self, start, end):
            calls.append((start, end))
            return {"job_id": "weekly-job", "state": "queued"}

        def close(self):
            pass

    monkeypatch.setattr("app.weekly_update.DiarisationClient", Backend)
    result = run_once(settings, datetime(2026, 9, 14, 8, tzinfo=timezone.utc))

    assert result == {"job_id": "weekly-job", "state": "queued"}
    assert calls == [(date(2026, 9, 7), date(2026, 9, 14))]
