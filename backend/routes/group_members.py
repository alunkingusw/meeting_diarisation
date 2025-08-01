# backend/routers/group_members.py
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import List
from backend.models import GroupMember, Group, GroupMemberOut
from backend.db_dependency import get_db
from backend.auth import get_current_user_id
from backend.validation import GroupMembersCreateEdit
from backend.config import settings
from backend.processing.generate_embedding import generate_embedding
import shutil
import os

router = APIRouter(prefix="/groups/{group_id}/members", tags=["group_members"])

@router.post("/")
def create_member(
        group_id: int,
        group_member_data: GroupMembersCreateEdit, 
        db: Session = Depends(get_db), 
        user_id: int = Depends(get_current_user_id)
    ):
    # check if group exists and belongs to the user
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    member = GroupMember(name=group_member_data.name)
    member.groups.append(group)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member

@router.get("/", response_model=List[GroupMemberOut])
def list_members(
        group_id: int,
        db: Session = Depends(get_db), 
        user_id: int = Depends(get_current_user_id),
        
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
        user_id: int = Depends(get_current_user_id),
        
    ):
    member = db.query(GroupMember).filter(
        GroupMember.id == member_id, GroupMember.group_id == group_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member

@router.put("/{member_id}")
def update_member(
        group_id:int,
        member_id: int, 
        group_member_data: GroupMembersCreateEdit,
        db: Session = Depends(get_db),
        user_id: int = Depends(get_current_user_id)
    ):
    member = db.query(GroupMember).filter(
        GroupMember.id == member_id, GroupMember.group_id == group_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.name = group_member_data.name
    db.commit()
    return member

@router.delete("/{member_id}")
def delete_member(
        group_id: int,
        member_id: int,
        db: Session = Depends(get_db),
        user_id: int = Depends(get_current_user_id)):
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
        user_id: int = Depends(get_current_user_id),
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
    file_name = f"{member_id}.wav"
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