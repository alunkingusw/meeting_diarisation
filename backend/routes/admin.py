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

"""Endpoints for trusted backend-to-backend callers only (see get_service_caller in
backend/auth.py) - never the per-user JWT flow. Kept to a finite, explicit set of read
endpoints, never a generic passthrough, matching the same trust-boundary principle
GroupAssessmentAgent (the caller these exist for) applies to its own LLM-facing schema."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from backend.db_dependency import get_db
from backend.auth import get_service_caller
from backend.models import Group, User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/group-owners", response_model=Dict[str, int])
def group_owners(
        db: Session = Depends(get_db),
        _=Depends(get_service_caller),
    ):
    """email -> user_id for every User with an email on file. There is no separate
    "owner" role in this schema (users_groups is a plain many-to-many) - any User with an
    email is authorised to act through GroupAssessmentAgent; per-group scoping happens
    separately via that user's own group membership."""
    users = db.query(User).filter(User.email.isnot(None)).all()
    return {user.email: user.id for user in users}


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
