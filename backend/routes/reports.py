# Copyright 2025 Alun King
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.auth import is_group_member
from backend.db_dependency import get_db
from backend.engine.report_graph import answer_report_question, compose_weekly_report
from backend.engine.report_schemas import (
    ReportAnswerRequest,
    ReportAnswerResponse,
    WeeklyReportRequest,
    WeeklyReportResponse,
)
from backend.jobs.schemas import JobAccepted
from backend.jobs.service import submit_job
from backend.llm.ollama_client import OllamaError
from backend.models import Group

router = APIRouter(prefix="/groups/{group_id}/reports", tags=["reports"])


def _get_group(db: Session, group_id: int) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.post("/weekly", response_model=WeeklyReportResponse, responses={202: {"model": JobAccepted}})
def weekly_report(
    group_id: int,
    payload: WeeklyReportRequest,
    run_async: bool = Query(
        False, alias="async",
        description="Run as a background job and return 202 with a job id to poll at GET /jobs/{id}.",
    ),
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_member),
):
    """Compose a cited report for meetings dated in [period_start, period_end) plus GitHub and
    Trello activity. Stateless: nothing is stored or emailed; the caller owns delivery."""
    if payload.period_end <= payload.period_start:
        raise HTTPException(status_code=422, detail="period_end must be after period_start")
    group = _get_group(db, group_id)
    if run_async:
        job = submit_job(
            db, "report",
            {
                "group_id": group_id, "period_start": payload.period_start.isoformat(),
                "period_end": payload.period_end.isoformat(),
            },
            user_id=user_id, group_id=group_id,
        )
        return JSONResponse(status_code=202, content=JobAccepted(job_id=job.id).model_dump())
    try:
        return compose_weekly_report(db, group, payload.period_start, payload.period_end)
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/answer", response_model=ReportAnswerResponse)
def answer_question(
    group_id: int,
    payload: ReportAnswerRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_member),
):
    """Answer a follow-up question using only the evidence from a previously composed report."""
    group = _get_group(db, group_id)
    try:
        return answer_report_question(group, payload)
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
