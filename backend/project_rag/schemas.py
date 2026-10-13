"""Request/response contracts for the group-scoped GitHub, Trello, conversation and unified query API."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceName = Literal["conversation", "github", "trello"]


class IngestSummary(BaseModel):
    """
    Counts are newly added records, so a second run over unchanged data reports
    zeros. `status` is "running" when a large repo was handed to a background task;
    poll the ingest status endpoint for completion.
    """

    group_id: int
    status: Literal["completed", "running"] = "completed"
    job_id: str | None = Field(default=None, description="Poll GET /jobs/{job_id} while status is running.")
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
        default=None, description="Inclusive start date for activity."
    )
    until: date | None = Field(default=None, description="Exclusive end date for activity.")

    @model_validator(mode="after")
    def validate_date_window(self) -> "QueryRequest":
        if self.since is not None and self.until is not None and self.since >= self.until:
            raise ValueError("until must be later than since")
        return self


class ConversationQueryRequest(QueryRequest):
    meeting_id: int | None = Field(default=None, description="Only this meeting's transcript.")
    retrieve_only: bool = Field(
        default=False,
        description="Return the matching transcript chunks as evidence without calling the LLM.",
    )


class UnifiedQueryRequest(QueryRequest):
    sources: list[SourceName] | None = Field(
        default=None,
        description="Sources to query. Omit to let the router infer them from the question.",
    )
    source_questions: dict[SourceName, str] = Field(
        default_factory=dict,
        description="Optional validated question per explicitly selected source.",
    )

    @model_validator(mode="after")
    def validate_source_questions(self) -> "UnifiedQueryRequest":
        if self.source_questions and self.sources is None:
            raise ValueError("source_questions requires an explicit sources list")
        normalized: dict[SourceName, str] = {}
        for source, question in self.source_questions.items():
            question = question.strip()
            if not 3 <= len(question) <= 2000:
                raise ValueError("each source question must contain 3 to 2000 characters")
            if self.sources is not None and source not in self.sources:
                raise ValueError(f"source question for {source} requires that source to be selected")
            normalized[source] = question
        self.source_questions = normalized
        return self


class EvidenceItem(BaseModel):
    id: str
    source_type: str
    author: str | None = None
    timestamp: str | None = None
    distance: float | None = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TranscriptSpeakerStatsResponse(BaseModel):
    speaker: str
    total_duration_sec: float
    total_words: int
    turn_count: int
    avg_words_per_turn: float
    meeting_time_share_pct: float
    meetings_spoken: int


class TranscriptMeetingStatsResponse(BaseModel):
    meeting_id: int
    meeting_title: str
    meeting_date: date
    total_duration_sec: float
    speakers: list[TranscriptSpeakerStatsResponse]


class TranscriptStatsResponse(BaseModel):
    """Deterministic speaker metrics loaded from indexed transcript stats artifacts."""

    complete: bool
    total_meetings: int
    total_duration_sec: float
    missing_meeting_ids: list[int] = Field(default_factory=list)
    speakers: list[TranscriptSpeakerStatsResponse]
    meetings: list[TranscriptMeetingStatsResponse]


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
        description="True if `evidence` is every record in the requested date window, not a relevance sample.",
    )
    stats: ProjectStatsResponse | None = None
    transcript_stats: TranscriptStatsResponse | None = None


class UnifiedQueryResponse(BaseModel):
    question: str
    answer: str
    model: str
    sources_used: list[SourceName]
    results: dict[str, SourceQueryResponse]
    errors: dict[str, str] = Field(
        default_factory=dict, description="Per-source failures; other sources still answer."
    )
