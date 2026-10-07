"""Request/response contracts for group reports."""
from datetime import date

from pydantic import BaseModel, Field


class ReportEvidenceItem(BaseModel):
    source: str = Field(description="meetings, github or trello")
    evidence_id: str
    title: str
    event_date: str | None = None
    content: str
    citation: str


class WeeklyReportRequest(BaseModel):
    period_start: date
    period_end: date = Field(description="Exclusive: meetings dated before this date.")


class WeeklyReportResponse(BaseModel):
    group_id: int
    group_name: str
    period_start: date
    period_end: date
    report_text: str
    model: str
    evidence: list[ReportEvidenceItem]
    unavailable: list[str] = Field(
        default_factory=list, description="Linked sources that could not be read for this report."
    )


class ReportAnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    period_start: date
    period_end: date
    evidence: list[ReportEvidenceItem]


class ReportAnswerResponse(BaseModel):
    answer: str
    model: str
