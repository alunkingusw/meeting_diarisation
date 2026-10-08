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

"""Finite identity and read endpoints for trusted backend-to-backend callers (see
get_service_caller in backend/auth.py). Service callers can resolve verified sender emails to
short-lived user or group-scoped member tokens, but do not receive a generic backend passthrough."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from backend.db_dependency import get_db
from backend.auth import EMAIL_CHANNEL, create_token_for_group_members, create_token_for_user, get_service_caller
from backend.engine.report_graph import answer_report_question
from backend.engine.report_schemas import (
    ReportAnswerRequest,
    ReportPeriodRequest,
    WeeklyReportServiceAnswerRequest,
)
from backend.jobs.schemas import accepted_response
from backend.jobs.service import submit_job
from backend.llm.ollama_client import OllamaError
from backend.models import Group, GroupMember, Job, User, WeeklyReport, users_groups
from backend.validation import ServiceUserTokenRequest

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/user-token")
def user_token(
        request: ServiceUserTokenRequest,
        db: Session = Depends(get_db),
        _=Depends(get_service_caller),
    ):
    """Resolve a verified service-caller email to a short-lived User or GroupMember JWT.

    User records are preferred when an email exists in both tables. Member tokens are
    restricted by member-to-group associations in the authorization dependencies. The agent
    must verify the inbound message's sender authentication before calling this endpoint.
    """
    user = (
        db.query(User)
        .filter(func.lower(func.trim(User.email)) == request.email.lower())
        .order_by(User.id)
        .first()
    )
    if user:
        return {"access_token": create_token_for_user(user.id, channel=EMAIL_CHANNEL), "token_type": "bearer"}

    members = (
        db.query(GroupMember)
        .filter(
            func.lower(func.trim(GroupMember.email)) == request.email.lower(),
            GroupMember.groups.any(),
        )
        .order_by(GroupMember.id)
        .all()
    )
    if not members:
        raise HTTPException(status_code=404, detail="User or group member not found")
    return {
        "access_token": create_token_for_group_members([member.id for member in members]),
        "token_type": "bearer",
    }


@router.get("/group-owners", response_model=Dict[str, int])
def group_owners(
        db: Session = Depends(get_db),
        _=Depends(get_service_caller),
    ):
    """email -> user_id for every User with an email on file, used for inbound mail
    authorization. Scheduled report recipients are separately restricted to owner links."""
    users = (
        db.query(User)
        .filter(User.email.isnot(None))
        .order_by(User.id)
        .all()
    )
    result: dict[str, int] = {}
    for user in users:
        email = user.email.strip().lower()
        if email:
            result.setdefault(email, user.id)
    return result


@router.get("/group-members", response_model=Dict[str, List[int]])
def group_members(
        db: Session = Depends(get_db),
        _=Depends(get_service_caller),
    ):
    """email -> member IDs for GroupMember records associated with at least one group."""
    members = (
        db.query(GroupMember)
        .filter(GroupMember.email.isnot(None), GroupMember.groups.any())
        .order_by(GroupMember.id)
        .all()
    )
    result: dict[str, list[int]] = {}
    for member in members:
        email = member.email.strip().lower()
        if email:
            result.setdefault(email, []).append(member.id)
    return result


class GroupProjectInfo(BaseModel):
    group_id: int
    group_name: str
    github_repo_url: str
    trello_board_id: Optional[str] = None


@router.get("/groups", response_model=List[GroupProjectInfo])
def groups(
        db: Session = Depends(get_db),
        _=Depends(get_service_caller),
    ):
    """Every group that has a GitHub repo linked, for GitHub-RAGinator's
    scripts/sync_repos_from_diarisation.py to mirror into its own repo registration. Groups
    with no github_repo_url set are omitted - there is nothing for that script to do with them."""
    matched = db.query(Group).filter(Group.github_repo_url.isnot(None)).all()
    return [
        GroupProjectInfo(
            group_id=g.id,
            group_name=g.name,
            github_repo_url=g.github_repo_url,
            trello_board_id=g.trello_board_id,
        )
        for g in matched
    ]


@router.post("/weekly-reports/run", responses={202: {"description": "Weekly report batch queued"}})
def run_weekly_reports(
    request: ReportPeriodRequest,
    db: Session = Depends(get_db),
    _=Depends(get_service_caller),
):
    """Queue reports for every project with an emailed supervisor (owner role)."""
    if request.period_end <= request.period_start:
        raise HTTPException(status_code=422, detail="period_end must be after period_start")

    for active_job in db.query(Job).filter(
        Job.kind == "weekly_reports", Job.state.in_(["queued", "running"])
    ):
        params = active_job.params or {}
        if (
            params.get("period_start") == request.period_start.isoformat()
            and params.get("period_end") == request.period_end.isoformat()
        ):
            return accepted_response(active_job.id)

    owners_exist = db.query(users_groups.c.group_id).join(
        User, User.id == users_groups.c.user_id
    ).filter(
        users_groups.c.role == "owner", User.email.isnot(None)
    ).first()
    if owners_exist is None:
        return {"state": "completed", "queued_groups": 0}

    job = submit_job(
        db,
        "weekly_reports",
        {
            "period_start": request.period_start.isoformat(),
            "period_end": request.period_end.isoformat(),
        },
    )
    return accepted_response(job.id)


@router.post("/group-nudger/run", responses={202: {"description": "Group nudger batch queued"}})
def run_group_nudger(
    request: ReportPeriodRequest,
    db: Session = Depends(get_db),
    _=Depends(get_service_caller),
):
    """Queue reminders for opted-in owner groups without a meeting in the requested window."""
    if request.period_end <= request.period_start:
        raise HTTPException(status_code=422, detail="period_end must be after period_start")

    for active_job in db.query(Job).filter(
        Job.kind == "group_nudger", Job.state.in_(["queued", "running"])
    ):
        params = active_job.params or {}
        if (
            params.get("period_start") == request.period_start.isoformat()
            and params.get("period_end") == request.period_end.isoformat()
        ):
            return accepted_response(active_job.id)

    eligible_group = db.query(Group.id).join(
        users_groups, users_groups.c.group_id == Group.id
    ).join(
        User, User.id == users_groups.c.user_id
    ).filter(
        users_groups.c.role == "owner",
        User.email.isnot(None),
        Group.notify.is_(True),
    ).first()
    if eligible_group is None:
        return {"state": "completed", "nudged_groups": 0, "queued_recipients": 0}

    job = submit_job(
        db,
        "group_nudger",
        {
            "period_start": request.period_start.isoformat(),
            "period_end": request.period_end.isoformat(),
        },
    )
    return accepted_response(job.id)


@router.post("/weekly-reports/{report_id}/answer")
def answer_weekly_report_reply(
    report_id: str,
    request: WeeklyReportServiceAnswerRequest,
    db: Session = Depends(get_db),
    _=Depends(get_service_caller),
):
    """Answer an email follow-up only when its sender received the saved report."""
    report = db.get(WeeklyReport, report_id)
    sender = request.sender_email.strip().casefold()
    recipients = [address.casefold() for address in (report.queued_recipients or [])] if report else []
    if report is None or sender not in recipients:
        raise HTTPException(status_code=404, detail="Weekly report not found")
    if report.evidence is None or report.report_text is None:
        raise HTTPException(status_code=409, detail="Weekly report evidence is not available")

    group = db.get(Group, report.group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Weekly report not found")
    try:
        answer = answer_report_question(
            group,
            ReportAnswerRequest(
                question=request.question,
                period_start=report.period_start,
                period_end=report.period_end,
                evidence=report.evidence,
            ),
        )
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return answer
