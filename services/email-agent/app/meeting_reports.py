"""Small in-process timer that triggers the backend-owned weekly report workflow."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.settings import Settings

logger = logging.getLogger(__name__)


def next_run(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    candidate += timedelta(days=(weekday - now.weekday()) % 7)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def run_scheduler(settings: Settings, stop_event: threading.Event) -> None:
    from app.weekly_update import run_once

    cfg = settings.meeting_report
    zone = ZoneInfo(settings.storage.default_timezone)
    while not stop_event.is_set():
        now = datetime.now(zone)
        target = next_run(now, cfg.weekday, cfg.hour, cfg.minute)
        logger.info("Next weekly project update run at %s", target.isoformat())
        if stop_event.wait((target - now).total_seconds()):
            return
        try:
            result = run_once(settings, datetime.now(zone))
            logger.info("Weekly report batch accepted by backend: %s", result)
        except Exception:
            logger.exception("Weekly project update run failed")
