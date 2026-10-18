from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ReportEvidence:
    source: str
    evidence_id: str
    title: str
    event_date: Optional[str]
    content: str
    citation: str
    raw_json: str