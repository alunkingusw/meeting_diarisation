"""Admin alerting: notifies ADMIN_EMAIL of things a human should look at.

Rate-limited per category (default 15 min cooldown) so a prolonged outage doesn't send one
email per poll cycle. Delivery goes through the same Outbox as user-facing mail, so admin
alerts get the same send-retry treatment (spec S20's "email sending fails" case).

Deliberately narrow: only the categories below ever trigger an alert. Ordinary user
mistakes handled by a normal clarification/rejection reply (wrong file type, ambiguous group,
etc.) are NOT admin-alertable - see commands/validator.py's Rejected/ClarificationRequired.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from app.jobs.store import Outbox
from app.storage.db import get_connection


class AdminCategory(str, Enum):
    UNAUTHORISED_SENDER = "unauthorised_sender"
    LLM_PARSE_FAILURE = "llm_parse_failure"
    BACKEND_SUBMISSION_FAILURE = "backend_submission_failure"
    BACKEND_COMMENT_FAILURE = "backend_comment_failure"
    ASSESS_QUERY_FAILURE = "assess_query_failure"
    INFRASTRUCTURE = "infrastructure"


class AdminNotifier:
    def __init__(
        self,
        db_path: Path,
        outbox: Outbox,
        admin_email: Optional[str],
        cooldown_minutes: float = 15.0,
    ):
        self._db_path = Path(db_path)
        self._outbox = outbox
        self._admin_email = admin_email
        self._cooldown = timedelta(minutes=cooldown_minutes)

    def alert(self, category: AdminCategory, summary: str, detail: Optional[dict] = None) -> bool:
        """Enqueues an admin alert email. Returns False (no-op) if no admin email is
        configured, or if this category is still within its cooldown window."""
        if not self._admin_email:
            return False
        if not self._should_send(category):
            return False

        body_lines = [summary, ""]
        if detail:
            body_lines.append("Details:")
            for key, value in detail.items():
                body_lines.append(f"  {key}: {value}")

        self._outbox.enqueue(
            to_email=self._admin_email,
            subject=f"[GroupAssessmentAgent] {category.value.replace('_', ' ').title()}",
            body_text="\n".join(body_lines),
        )
        self._record_sent(category)
        return True

    def _should_send(self, category: AdminCategory) -> bool:
        conn = get_connection(self._db_path)
        try:
            row = conn.execute(
                "SELECT last_sent_at FROM admin_alerts WHERE category = ?", (category.value,)
            ).fetchone()
            if row is None:
                return True
            last_sent = datetime.fromisoformat(row["last_sent_at"])
            return datetime.now(timezone.utc) - last_sent >= self._cooldown
        finally:
            conn.close()

    def _record_sent(self, category: AdminCategory) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection(self._db_path)
        try:
            conn.execute(
                """INSERT INTO admin_alerts (category, last_sent_at) VALUES (?, ?)
                   ON CONFLICT(category) DO UPDATE SET last_sent_at = excluded.last_sent_at""",
                (category.value, now),
            )
        finally:
            conn.close()
