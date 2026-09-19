"""One-shot weekly report entry point for cron or a system scheduler."""
from __future__ import annotations

import argparse
from pathlib import Path
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.admin.notifier import AdminNotifier
from app.diarisation.client import DiarisationClient
from app.github_raginator.client import GithubRaginatorClient
from app.jobs.store import Outbox
from app.llm.ollama_client import OllamaClient
from app.logging_config import configure_logging
from app.main import build_mail_client, load_group_owners
from app.reports.store import ReportStore
from app.reports.workflow import WeeklyReportWorkflow
from app.settings import Settings, load_settings
from app.storage.db import init_db

logger = logging.getLogger(__name__)


def reporting_period(settings: Settings, now: datetime | None = None) -> tuple[date, date]:
    zone = (
        timezone.utc
        if settings.storage.default_timezone.upper() == "UTC"
        else ZoneInfo(settings.storage.default_timezone)
    )
    current = (now or datetime.now(zone)).date()
    end = current
    start = end - timedelta(days=settings.weekly_update.lookback_days)
    return start, end


def run_once(settings: Settings, now: datetime | None = None) -> int:
    settings.ensure_storage_dirs()
    configure_logging(settings)
    init_db(settings.storage.db_path)

    owners = load_group_owners(settings)
    if not owners:
        logger.warning("No authorised group owners configured; no weekly reports generated")
        return 0

    mail_client = build_mail_client(settings)
    outbox = Outbox(settings.storage.db_path)
    report_store = ReportStore(settings.storage.db_path)
    admin = AdminNotifier(
        settings.storage.db_path, outbox, settings.admin_email,
        settings.admin.alert_cooldown_minutes,
    )
    diarisation = DiarisationClient(
        settings.backend.base_url,
        settings.backend.request_timeout_seconds,
        settings.backend.max_retry_attempts,
        settings.backend.retry_backoff_seconds,
        settings.diarisation_service_api_key,
    )
    github = GithubRaginatorClient(
        settings.github_raginator.base_url,
        settings.github_raginator.request_timeout_seconds,
        settings.github_raginator.max_retry_attempts,
        settings.github_raginator.retry_backoff_seconds,
    )
    ollama = OllamaClient(
        settings.llm.host, settings.llm.model, settings.llm.request_timeout_seconds
    )
    workflow = WeeklyReportWorkflow(report_store, outbox, diarisation, github, ollama, admin)
    period_start, period_end = reporting_period(settings, now)
    generated = 0

    try:
        for owner_email, user_id in owners.items():
            try:
                token = diarisation.login(user_id)
                groups = diarisation.list_groups(token)
            except Exception:
                logger.exception("Could not list groups for weekly owner %s", owner_email)
                continue
            for group in groups:
                report = report_store.create_or_get(
                    group.id, group.name, owner_email, user_id,
                    period_start.isoformat(), period_end.isoformat(),
                )
                workflow.run(report.report_id)
                generated += 1
        _flush_report_outbox(mail_client, outbox, report_store)
        return generated
    finally:
        ollama.close()
        diarisation.close()
        github.close()


def _flush_report_outbox(mail_client, outbox: Outbox, report_store: ReportStore) -> None:
    for message in outbox.pending():
        if not message.job_id or not message.job_id.startswith("WEEKLY-"):
            continue
        try:
            attachments = (
                [(Path(path).name, Path(path).read_bytes()) for path in message.attachments]
                if message.attachments else None
            )
            provider_id = mail_client.send_email(
                to=message.to_email,
                subject=message.subject,
                body_text=message.body_text,
                attachments=attachments,
                in_reply_to=message.in_reply_to_message_id,
                references=message.references_header,
            )
            outbox.mark_sent(message.id, provider_id)
            report_store.set_status(message.job_id, "SENT")
        except Exception:
            logger.exception("Could not send weekly report outbox message %s", message.id)
            outbox.mark_failed(message.id, "weekly report send failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate weekly group project updates")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    settings = load_settings(args.config)
    if not settings.weekly_update.enabled:
        logger.info("weekly_update.enabled is false; nothing to do")
        return
    run_once(settings)


if __name__ == "__main__":
    main()
