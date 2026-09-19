from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ReportEvidence:
    source: str
    evidence_id: str
    title: str
    event_date: Optional[str]
    content: str
    citation: str
    raw_json: str


@dataclass
class WeeklyReport:
    report_id: str
    group_id: int
    group_name: str
    owner_email: str
    backend_user_id: int
    period_start: str
    period_end: str
    status: str
    report_text: Optional[str] = None
    last_error: Optional[str] = None
    created_at: str = ""
    completed_at: Optional[str] = None
