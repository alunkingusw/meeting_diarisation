"""Request/response contracts for the group-scoped GitHub, Trello, conversation and unified query API."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceName = Literal["conversation", "github", "trello"]


class IngestSummary(BaseModel):
    """
    Counts are newly added records, so a second run over unchanged data reports
    zeros. `status` is "running" when a large repo was handed to a background task;
    poll the ingest status endpoint for completion.
    """

    group_id: int
    status: Literal["completed", "running"] = "completed"
    commits_ingested: int | None = None
    issues_ingested: int | None = None
    issue_comments_ingested: int | None = None
    review_comments_ingested: int | None = None
    trello_actions_ingested: int | None = None
    warnings: list[str] = Field(default_factory=list)


class IngestStatus(BaseModel):
    group_id: int
    github_url: str | None
    trello_board_id: str | None
    last_synced_at: datetime | None
    trello_last_synced_at: datetime | None
    ingest_status: Literal["idle", "running", "failed"]
    ingest_error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ContributorStatsResponse(BaseModel):
    name: str
    commits: int
    additions: int
    deletions: int
    issues_opened: int
    issue_comments: int
    review_comments: int
    trello_actions: int
    first_commit_at: datetime | None
    last_commit_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class WeeklyActivityResponse(BaseModel):
    week_starting: datetime
    commits: int
    authors: int

    model_config = ConfigDict(from_attributes=True)


class ProjectStatsResponse(BaseModel):
    """Facts computed from Postgres with no LLM involved."""

    repo_id: int
    repo_name: str
    total_commits: int
    total_issues: int
    open_issues: int
    closed_issues: int
    total_issue_comments: int
    total_review_comments: int
    total_trello_actions: int
    first_activity_at: datetime | None
    last_activity_at: datetime | None
    last_synced_at: datetime | None
    contributors: list[ContributorStatsResponse]
    weekly_activity: list[WeeklyActivityResponse]

    model_config = ConfigDict(from_attributes=True)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    since: date | None = Field(
        default=None, description="Only consider activity on or after this date."
    )


class ConversationQueryRequest(QueryRequest):
    until: date | None = Field(
        default=None, description="Only meetings dated before this date (exclusive)."
    )
    retrieve_only: bool = Field(
        default=False,
        description="Return the matching transcript chunks as evidence without calling the LLM.",
    )


class UnifiedQueryRequest(QueryRequest):
    sources: list[SourceName] | None = Field(
        default=None,
        description="Sources to query. Omit to let the router infer them from the question.",
    )


class EvidenceItem(BaseModel):
    id: str
    source_type: str
    author: str | None = None
    timestamp: str | None = None
    distance: float | None = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceQueryResponse(BaseModel):
    """An answer plus the evidence it was built from."""

    source: SourceName
    question: str
    answer: str = ""
    model: str | None = None
    evidence: list[EvidenceItem]
    truncated_evidence: int = 0
    complete_window: bool = Field(
        default=False,
        description="True if `evidence` is every record in the `since` window, not a relevance sample.",
    )
    stats: ProjectStatsResponse | None = None


class UnifiedQueryResponse(BaseModel):
    question: str
    answer: str
    model: str
    sources_used: list[SourceName]
    results: dict[str, SourceQueryResponse]
    errors: dict[str, str] = Field(
        default_factory=dict, description="Per-source failures; other sources still answer."
    )
