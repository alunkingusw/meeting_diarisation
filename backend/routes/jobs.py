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
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.auth import EmailPrincipal, _is_admin, get_email_principal, get_group_role
from backend.db_dependency import get_db
from backend.jobs import service
from backend.jobs.schemas import JobOut
from backend.models import Group, Job, users_groups

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _owned_group_ids(db: Session, user_id: int):
    return db.query(users_groups.c.group_id).filter(
        users_groups.c.user_id == user_id, users_groups.c.role == "owner"
    )


def _can_view(db: Session, principal: EmailPrincipal, job: Job) -> bool:
    if principal.user_id is not None:
        if job.user_id == principal.user_id:
            return True
        if job.group_id is not None and get_group_role(db, principal.user_id, job.group_id) == "owner":
            return True
        return _is_admin(db, principal.user_id, principal.channel)
    return job.group_member_id is not None and job.group_member_id in principal.group_member_ids


def _can_cancel(db: Session, principal: EmailPrincipal, job: Job) -> bool:
    return principal.user_id is not None and _can_view(db, principal, job)


def _get_visible(db: Session, principal: EmailPrincipal, job_id: str) -> Job:
    job = db.get(Job, job_id)
    # Same answer for missing and not-yours, so job ids can't be probed.
    if job is None or not _can_view(db, principal, job):
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/", response_model=list[JobOut])
def list_jobs(
    kind: str | None = None,
    state: str | None = None,
    group_id: int | None = None,
    meeting_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: EmailPrincipal = Depends(get_email_principal),
):
    """Jobs you started, plus jobs in groups you own. Newest first."""
    query = db.query(Job)
    if principal.user_id is not None:
        visible = [Job.user_id == principal.user_id, Job.group_id.in_(_owned_group_ids(db, principal.user_id))]
        query = query.filter(or_(*visible))
    else:
        query = query.filter(Job.group_member_id.in_(principal.group_member_ids))
    for column, value in ((Job.kind, kind), (Job.state, state), (Job.group_id, group_id), (Job.meeting_id, meeting_id)):
        if value is not None:
            query = query.filter(column == value)
    return query.order_by(Job.created_at.desc()).limit(limit).all()


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    principal: EmailPrincipal = Depends(get_email_principal),
):
    return _get_visible(db, principal, job_id)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    principal: EmailPrincipal = Depends(get_email_principal),
):
    """Cancel a queued job at once, or ask a running one to stop at its next checkpoint (an LLM call
    already in progress finishes first)."""
    job = _get_visible(db, principal, job_id)
    if not _can_cancel(db, principal, job):
        raise HTTPException(status_code=403, detail="Not authorised to cancel this job")
    if job.state in service.TERMINAL_STATES:
        raise HTTPException(status_code=409, detail=f"Job is already {job.state}")
    return service.request_cancel(db, job)
