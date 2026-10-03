"""Scheduled trigger for the backend's POST /reports/generate_report (one email per supervised group)."""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.diarisation.client import DiarisationApiError, DiarisationClient
from app.settings import Settings

logger = logging.getLogger(__name__)


def report_period(settings: Settings, now: datetime) -> tuple[date, date]:
    """Inclusive window ending today and covering lookback_days days."""
    end = now.date()
    return end - timedelta(days=settings.weekly_update.lookback_days - 1), end


def next_run(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    candidate += timedelta(days=(weekday - now.weekday()) % 7)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def send_meeting_reports(
    settings: Settings,
    client: DiarisationClient,
    owners: dict[str, int],
    now: datetime,
) -> int:
    start, end = report_period(settings, now)
    sent = 0
    for owner_email, user_id in owners.items():
        try:
            token = client.login(user_id)
            results = client.generate_report(token, start, end)
        except DiarisationApiError:
            logger.exception("Could not generate meeting report for %s", owner_email)
            continue
        sent += sum(1 for r in results if r.get("emailed"))
    return sent


def run_scheduler(
    settings: Settings,
    client: DiarisationClient,
    load_owners,
    stop_event: threading.Event,
) -> None:
    cfg = settings.meeting_report
    zone = ZoneInfo(settings.storage.default_timezone)
    while not stop_event.is_set():
        now = datetime.now(zone)
        target = next_run(now, cfg.weekday, cfg.hour, cfg.minute)
        logger.info("Next meeting report run at %s", target.isoformat())
        if stop_event.wait((target - now).total_seconds()):
            return
        try:
            count = send_meeting_reports(settings, client, load_owners(settings), datetime.now(zone))
            logger.info("Meeting reports emailed: %s", count)
        except Exception:
            logger.exception("Meeting report run failed")
