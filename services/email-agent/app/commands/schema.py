"""The strict, application-owned structured command schema.

This is the sole channel through which the LLM's interpretation of an email can influence
application behaviour. The LLM's raw output is never trusted merely because it is valid JSON:
it must validate against this schema (extra fields are rejected outright), and even a fully
valid ParsedCommand is still subject to further deterministic checks in commands/validator.py
before anything is executed.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JOB_ID_PATTERN = re.compile(r"^DIAR-\d{4}-\d{4}-\d{4}$")

# Characters that would turn an "attachment filename" into a path traversal / absolute path.
_PATH_TRAVERSAL_CHARS = ("/", "\\", "\x00")


class Operation(str, Enum):
    SUBMIT_TRANSCRIPT = "submit_transcript"
    STATUS = "status"
    RESULTS = "results"
    CANCEL = "cancel"
    ASSESS_QUERY = "assess_query"
    ADD_COMMENT = "add_comment"
    HELP = "help"


class CommandParsingFailed(Exception):
    """Raised when the LLM's output cannot be turned into a valid ParsedCommand, even after
    retries. A parsing failure must never be silently coerced into a default/guessed command."""


class ParsedCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Operation
    attachment: Optional[str] = Field(default=None, max_length=255)
    group_hint: Optional[str] = Field(default=None, max_length=200)
    job_id: Optional[str] = Field(default=None, pattern=JOB_ID_PATTERN.pattern)
    mentioned_date: Optional[str] = Field(default=None, max_length=64)
    return_statistics: bool = False
    transcript_focus: Optional[str] = Field(default=None, max_length=300)
    github_focus: Optional[str] = Field(default=None, max_length=300)
    trello_focus: Optional[str] = Field(default=None, max_length=300)
    comment: Optional[str] = Field(default=None, max_length=20000)
    requires_clarification: bool = False
    clarification_question: Optional[str] = Field(default=None, max_length=500)

    @field_validator("attachment")
    @classmethod
    def _attachment_no_path_chars(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if any(ch in v for ch in _PATH_TRAVERSAL_CHARS) or ".." in v:
            raise ValueError("attachment must be a bare filename, not a path")
        return v

    @field_validator(
        "attachment",
        "group_hint",
        "clarification_question",
        "mentioned_date",
        "transcript_focus",
        "github_focus",
        "trello_focus",
        "comment",
    )
    @classmethod
    def _strip_and_reject_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None

    @model_validator(mode="after")
    def _clarification_requires_question(self) -> "ParsedCommand":
        if self.requires_clarification and not self.clarification_question:
            raise ValueError(
                "clarification_question is required when requires_clarification is true"
            )
        return self
