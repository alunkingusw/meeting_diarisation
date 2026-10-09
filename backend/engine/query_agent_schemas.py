"""Shared contracts for source query specialists and their parent workflow.

These schemas are additive design contracts; current API handlers do not use them yet.
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.project_rag.schemas import EvidenceItem, SourceName


class QueryFilters(BaseModel):
    """User-requested time/meeting filters, validated by application code."""

    model_config = ConfigDict(extra="forbid")

    since: date | None = Field(default=None, description="Inclusive start date.")
    until: date | None = Field(default=None, description="Exclusive end date.")
    meeting_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_date_range(self) -> "QueryFilters":
        if self.since is not None and self.until is not None and self.since >= self.until:
            raise ValueError("until must be later than since")
        return self


class SpecialistQueryInput(BaseModel):
    """Model-visible arguments; deliberately contains no identity or group authority."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=2000)
    filters: QueryFilters = Field(default_factory=QueryFilters)


class TrustedQueryContext(BaseModel):
    """Application-supplied scope after authentication and authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: int
    group_id: int
    allowed_sources: list[SourceName] = Field(min_length=1)


class QuantitativeFact(BaseModel):
    """A deterministic metric with enough context to interpret and audit it."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: int | float
    unit: str = Field(min_length=1)
    scope: dict[str, str | int | float] = Field(
        description="Group, meeting, date-window, or other aggregation scope."
    )
    provenance: list[str] = Field(
        min_length=1,
        description="Source records or deterministic aggregation that produced this fact.",
    )
    completeness: Literal["complete", "sampled", "unknown"]


class SpecialistQueryResult(BaseModel):
    """Source answer plus structured facts and cited retrieval evidence."""

    model_config = ConfigDict(extra="forbid")

    source: SourceName
    question: str
    answer: str
    quantitative_facts: list[QuantitativeFact] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    model: str | None = None
    retrieval_metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)