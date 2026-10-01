# backend/routers/groups.py

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
from sqlalchemy.orm import Session
from backend.models import Group, GroupMember, User, GroupOut
from backend.db_dependency import get_db
from backend.auth import (
    get_current_user_id,
    get_email_principal,
    is_group_member,
    is_group_owner,
    EmailPrincipal,
)
from backend.validation import GroupCreateEdit


router = APIRouter(prefix="/groups", tags=["groups"])

@router.post("/")
def create_group(group_data: GroupCreateEdit, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    owner = user
    if group_data.owner_user_id is not None and group_data.owner_user_id != user_id:
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="Administrator permission required to assign a different owner")
        owner = db.query(User).filter(User.id == group_data.owner_user_id).first()
        if not owner:
            raise HTTPException(status_code=404, detail="Owner user not found")

    new_group = Group(
        name=group_data.name,
        github_repo_url=group_data.github_repo_url,
        trello_board_id=group_data.trello_board_id,
        notify=group_data.notify,
    )
    new_group.users.append(owner)  # Associate this group with the owner
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group

@router.get("/")
def list_groups(
        db: Session = Depends(get_db),
        principal: EmailPrincipal = Depends(get_email_principal),
        all_groups: bool = Query(False, description="Admins only: list every group, not just ones you belong to"),
    ):
    if all_groups:
        user = db.query(User).filter(User.id == principal.user_id).first()
        if not user or not user.is_admin:
            raise HTTPException(status_code=403, detail="Administrator permission required")
        return db.query(Group).order_by(Group.id).all()

    if principal.user_id is not None:
        user = db.query(User).filter(User.id == principal.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user.groups

    member_groups = (
        db.query(Group)
        .filter(Group.members.any(GroupMember.id.in_(principal.group_member_ids)))
        .order_by(Group.id)
        .all()
    )
    return [{"id": group.id, "name": group.name} for group in member_groups]

@router.get("/{group_id}", response_model=GroupOut)
def get_group(group_id: int, db: Session = Depends(get_db), user_id:int = Depends(is_group_member)):
    group = db.query(Group).get(group_id)
    return group

@router.put("/{group_id}")
def update_group(group_id: int, group_data: GroupCreateEdit, db: Session = Depends(get_db), user_id:int = Depends(is_group_owner)):
    group = db.query(Group).get(group_id)
    group.name = group_data.name
    group.github_repo_url = group_data.github_repo_url
    group.trello_board_id = group_data.trello_board_id
    group.notify = group_data.notify
    db.commit()
    db.refresh(group)
    return group

@router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), user_id:int = Depends(is_group_owner)):
    group = db.query(Group).get(group_id)
    db.delete(group)
    db.commit()
    return {"message": "Group deleted"}