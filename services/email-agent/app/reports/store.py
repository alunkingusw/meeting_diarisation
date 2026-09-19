from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.jobs.store import utcnow_iso
from app.reports.models import ReportEvidence, WeeklyReport
from app.storage.db import get_connection


class ReportStore:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self._db_path)

    def create_or_get(
        self,
        group_id: int,
        group_name: str,
        owner_email: str,
        backend_user_id: int,
        period_start: str,
        period_end: str,
    ) -> WeeklyReport:
        report_id = f"WEEKLY-{period_start}-{group_id:04d}"
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO weekly_reports
                   (report_id, group_id, group_name, owner_email, backend_user_id,
                    period_start, period_end, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'RECEIVED', ?)
                   ON CONFLICT(group_id, period_start, period_end) DO NOTHING""",
                (report_id, group_id, group_name, owner_email, backend_user_id,
                 period_start, period_end, utcnow_iso()),
            )
        finally:
            conn.close()
        return self.get_by_period(group_id, period_start, period_end)  # type: ignore[return-value]

    def get(self, report_id: str) -> Optional[WeeklyReport]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM weekly_reports WHERE report_id = ?", (report_id,)
            ).fetchone()
            return _report_from_row(row) if row else None
        finally:
            conn.close()

    def get_by_period(self, group_id: int, period_start: str, period_end: str) -> Optional[WeeklyReport]:
        conn = self._conn()
        try:
            row = conn.execute(
                """SELECT * FROM weekly_reports
                   WHERE group_id = ? AND period_start = ? AND period_end = ?""",
                (group_id, period_start, period_end),
            ).fetchone()
            return _report_from_row(row) if row else None
        finally:
            conn.close()

    def get_by_message_id(self, message_id: str, recipient: str) -> Optional[WeeklyReport]:
        conn = self._conn()
        try:
            row = conn.execute(
                """SELECT weekly_reports.* FROM weekly_reports
                   JOIN message_links ON message_links.job_id = weekly_reports.report_id
                   WHERE message_links.message_id = ?
                     AND LOWER(weekly_reports.owner_email) = LOWER(?)
                   ORDER BY message_links.created_at DESC LIMIT 1""",
                (message_id, recipient),
            ).fetchone()
            return _report_from_row(row) if row else None
        finally:
            conn.close()

    def set_status(self, report_id: str, status: str, report_text: Optional[str] = None,
                   error: Optional[str] = None) -> None:
        conn = self._conn()
        try:
            completed_at = utcnow_iso() if status in {"COMPLETED", "FAILED"} else None
            conn.execute(
                """UPDATE weekly_reports
                   SET status = ?, report_text = COALESCE(?, report_text),
                       last_error = ?, completed_at = COALESCE(?, completed_at)
                   WHERE report_id = ?""",
                (status, report_text, error, completed_at, report_id),
            )
        finally:
            conn.close()

    def replace_evidence(self, report_id: str, evidence: list[ReportEvidence]) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM report_evidence WHERE report_id = ?", (report_id,))
            conn.executemany(
                """INSERT INTO report_evidence
                   (report_id, source, evidence_id, title, event_date, content,
                    citation, raw_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (report_id, item.source, item.evidence_id, item.title, item.event_date,
                     item.content, item.citation, item.raw_json, utcnow_iso())
                    for item in evidence
                ],
            )
        finally:
            conn.close()

    def evidence(self, report_id: str) -> list[ReportEvidence]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM report_evidence WHERE report_id = ? ORDER BY source, id",
                (report_id,),
            ).fetchall()
            return [
                ReportEvidence(
                    source=row["source"], evidence_id=row["evidence_id"], title=row["title"],
                    event_date=row["event_date"], content=row["content"],
                    citation=row["citation"], raw_json=row["raw_json"],
                )
                for row in rows
            ]
        finally:
            conn.close()


def _report_from_row(row: sqlite3.Row) -> WeeklyReport:
    return WeeklyReport(
        report_id=row["report_id"], group_id=row["group_id"], group_name=row["group_name"],
        owner_email=row["owner_email"], backend_user_id=row["backend_user_id"],
        period_start=row["period_start"], period_end=row["period_end"], status=row["status"],
        report_text=row["report_text"], last_error=row["last_error"],
        created_at=row["created_at"], completed_at=row["completed_at"],
    )
