# backend/routers/group_members.py

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

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import List
from pathlib import Path
from string import Template
from backend.models import GroupMember, Group, GroupMemberOut, User, users_groups
from backend.db_dependency import get_db
from backend.auth import is_group_owner
from backend.validation import GroupMembersCreateEdit
from backend.config import settings
from backend.email_client import EmailError, send_email
from backend.processing.generate_embedding import generate_embedding
from backend.routes.upload import ALLOWED_AUDIO_EXTENSIONS
import logging
import shutil
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/groups/{group_id}/members", tags=["group_members"])

WELCOME_EMAIL_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "group_member_welcome_email.txt"


def _render_welcome_email(
    member: GroupMember, group: Group, owner_email: str
) -> tuple[str, str]:
    template_lines = WELCOME_EMAIL_TEMPLATE_PATH.read_text(encoding="utf-8").splitlines()
    template_text = "\n".join(line for line in template_lines if not line.startswith("#"))
    body = Template(template_text).substitute(
        member_name=member.name or "there",
        group_name=group.name or "Unnamed group",
        owner_email=owner_email or "not available",
    )
    subject = f"Welcome to {group.name or 'Unnamed group'}"
    return subject, body.strip()


def _send_welcome_email(member: GroupMember, group: Group, owner_email: str) -> None:
    if not member.email:
        logger.info("Notify requested for member %s but no email address is set", member.id)
        return
    try:
        subject, body = _render_welcome_email(member, group, owner_email)
        send_email(to=member.email.strip(), subject=subject, body=body)
    except EmailError:
        logger.exception("Could not send welcome email to member %s", member.id)


@router.post("/")
def create_member(
        group_id: int,
        group_member_data: GroupMembersCreateEdit,
        background_tasks: BackgroundTasks,
        notify: bool = Query(True, description="Send the member a welcome email once added"),
        db: Session = Depends(get_db), 
        user_id: int = Depends(is_group_owner)
    ):
    # check if group exists and belongs to the user
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    owner_emails = db.query(User.email).join(
        users_groups, users_groups.c.user_id == User.id
    ).filter(
        users_groups.c.group_id == group.id,
        users_groups.c.role == "owner",
        User.email.isnot(None),
    ).order_by(User.id).all()
    owner_email = ", ".join(email for (email,) in owner_emails if email)

    member = GroupMember(name=group_member_data.name, email=group_member_data.email)
    member.groups.append(group)
    db.add(member)
    db.commit()
    db.refresh(member)

    if notify:
        background_tasks.add_task(_send_welcome_email, member, group, owner_email)

    return member

@router.get("/", response_model=List[GroupMemberOut])
def list_members(
        group_id: int,
        db: Session = Depends(get_db), 
        user_id: int = Depends(is_group_owner),
        
    ):
    group = db.query(Group).get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Optional: check if user is part of the group
    if user_id not in [member.id for member in group.users]:
        raise HTTPException(status_code=403, detail="Not authorised to view this group's members")

    return group.members  # Access via relationship

@router.get("/{member_id}",response_model=GroupMemberOut)
def get_member(
        group_id:int,
        member_id: int, 
        db: Session = Depends(get_db), 
        user_id: int = Depends(is_group_owner),
        
    ):
    member = db.query(GroupMember).filter(
        GroupMember.id == member_id
    ).filter(GroupMember.groups.any(id=group_id)).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member

@router.put("/{member_id}")
def update_member(
        group_id:int,
        member_id: int, 
        group_member_data: GroupMembersCreateEdit,
        db: Session = Depends(get_db),
        user_id: int = Depends(is_group_owner)
    ):
    member = db.query(GroupMember).filter(
        GroupMember.id == member_id
    ).filter(GroupMember.groups.any(id=group_id)).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.name = group_member_data.name
    member.email = group_member_data.email
    db.commit()
    db.refresh(member)
    return member

@router.delete("/{member_id}")
def delete_member(
        group_id: int,
        member_id: int,
        db: Session = Depends(get_db),
        user_id: int = Depends(is_group_owner)):
    member = db.query(GroupMember).get(member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    db.commit()
    return {"message": "Member deleted"}

@router.post("/{member_id}/embedding")
def upload_member_embedding(
        group_id: int,
        member_id: int,
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        overwrite: bool = Query(False),
        db: Session = Depends(get_db),
        user_id: int = Depends(is_group_owner),
    ):
    # Validate group and member
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    member = db.query(GroupMember).filter(
        GroupMember.id == member_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Define path
    embedding_dir = settings.EMBEDDING_DIR
    embedding_dir.mkdir(parents=True, exist_ok=True)

    # Keep original extension (fall back to .wav if missing)
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()

    if not ext or ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. Allowed: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}"
        )
    
    file_name = f"{member_id}{ext}"
    audio_path = embedding_dir / file_name

    # Check for existing audio
    if audio_path.exists() and not overwrite:
        raise HTTPException(
            status_code=409,
            detail="Embedding audio already exists. Use `overwrite=true` to replace it."
        )

    # Save file
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    #update member with file name
    member.embedding_audio_path = file_name
    db.commit()

    # Queue background embedding process
    background_tasks.add_task(generate_embedding, member_id, db)

    return {
        "message": "Audio file uploaded. Embedding will be processed shortly.",
        "member_id": member_id,
        "file_name":file_name,
    }