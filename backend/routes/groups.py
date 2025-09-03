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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import Group, User, GroupOut
from backend.db_dependency import get_db
from backend.auth import is_group_user, get_current_user_id
from backend.validation import GroupCreateEdit


router = APIRouter(prefix="/groups", tags=["groups"])

@router.post("/")
def create_group(group_data: GroupCreateEdit, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_group = Group(name=group_data.name)
    new_group.users.append(user)  # Associate this group with the user
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group

@router.get("/")
def list_groups(db: Session = Depends(get_db), user_id:int = Depends(get_current_user_id)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.groups  # Only the groups associated with this user

@router.get("/{group_id}", response_model=GroupOut)
def get_group(group_id: int, db: Session = Depends(get_db), user_id:int = Depends(is_group_user)):
    group = db.query(Group).get(group_id)
    return group

@router.put("/{group_id}")
def update_group(group_id: int, name: str, group_data: GroupCreateEdit, db: Session = Depends(get_db), user_id:int = Depends(is_group_user)):
    group = db.query(Group).get(group_id)
    group.name = name
    db.commit()
    return group

@router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), user_id:int = Depends(is_group_user)):
    group = db.query(Group).get(group_id)
    db.delete(group)
    db.commit()
    return {"message": "Group deleted"}