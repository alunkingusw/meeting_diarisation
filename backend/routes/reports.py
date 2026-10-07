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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth import is_group_member
from backend.db_dependency import get_db, get_group_or_404
from backend.engine.report_graph import answer_report_question, compose_weekly_report
from backend.engine.report_schemas import (
    ReportAnswerRequest,
    ReportAnswerResponse,
    WeeklyReportRequest,
    WeeklyReportResponse,
)
from backend.jobs.schemas import ASYNC_PARAM, JobAccepted, accepted_response
from backend.jobs.service import submit_job
from backend.llm.ollama_client import OllamaError

router = APIRouter(prefix="/groups/{group_id}/reports", tags=["reports"])


@router.post("/weekly", response_model=WeeklyReportResponse, responses={202: {"model": JobAccepted}})
def weekly_report(
    group_id: int,
    payload: WeeklyReportRequest,
    run_async: bool = ASYNC_PARAM,
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_member),
):
    """Compose a cited report for meetings dated in [period_start, period_end) plus GitHub and
    Trello activity. Stateless: nothing is stored or emailed; the caller owns delivery."""
    if payload.period_end <= payload.period_start:
        raise HTTPException(status_code=422, detail="period_end must be after period_start")
    group = get_group_or_404(db, group_id)
    if run_async:
        job = submit_job(
            db, "report",
            {
                "group_id": group_id, "period_start": payload.period_start.isoformat(),
                "period_end": payload.period_end.isoformat(),
            },
            user_id=user_id, group_id=group_id,
        )
        return accepted_response(job.id)
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
    group = get_group_or_404(db, group_id)
    try:
        return answer_report_question(group, payload)
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
