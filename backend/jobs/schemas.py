from datetime import datetime
from typing import Any

from fastapi import Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class JobOut(BaseModel):
    id: str
    kind: str
    state: str = Field(description="queued, running, completed, failed or cancelled")
    group_id: int | None = None
    meeting_id: int | None = None
    progress: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    error_type: str | None = Field(default=None, description="Exception class name when the job failed")
    cancel_requested: bool = False
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class JobAccepted(BaseModel):
    job_id: str
    state: str = "queued"


ASYNC_PARAM = Query(
    False, alias="async",
    description="Run as a background job and return 202 with a job id to poll at GET /jobs/{id}.",
)


def accepted_response(job_id: str) -> JSONResponse:
    return JSONResponse(status_code=202, content=JobAccepted(job_id=job_id).model_dump())
