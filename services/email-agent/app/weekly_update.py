"""Thin trigger for the backend-owned weekly report workflow."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.diarisation.client import DiarisationClient
from app.logging_config import configure_logging
from app.settings import Settings, load_settings

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


def run_once(settings: Settings, now: datetime | None = None) -> dict:
    diarisation = DiarisationClient(
        settings.backend.base_url,
        settings.backend.request_timeout_seconds,
        settings.backend.max_retry_attempts,
        settings.backend.retry_backoff_seconds,
        settings.diarisation_service_api_key,
        settings.backend.query_timeout_seconds,
    )
    try:
        period_start, period_end = reporting_period(settings, now)
        return diarisation.run_weekly_reports(period_start, period_end)
    finally:
        diarisation.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate weekly group project updates")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    settings = load_settings(args.config)
    if not settings.weekly_update.enabled:
        logger.info("weekly_update.enabled is false; nothing to do")
        return
    configure_logging(settings)
    result = run_once(settings)
    logger.info("Weekly report batch accepted by backend: %s", result)


if __name__ == "__main__":
    main()
