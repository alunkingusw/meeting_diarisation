# backend/routers/group_members.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import GroupMember
from backend.db_dependency import get_db
from backend.auth import get_current_user_id
from backend.validation import GroupMembersCreateEdit

router = APIRouter(prefix="/group-members", tags=["group_members"])

@router.post("/")
def create_member(group_member_data: GroupMembersCreateEdit, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    member = GroupMember(name=group_member_data.get("name"))
    db.add(member)
    db.commit()
    db.refresh(member)
    return member

@router.get("/")
def list_members(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return db.query(GroupMember).all()

@router.get("/{member_id}")
def get_member(member_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    member = db.query(GroupMember).get(member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member

@router.put("/{member_id}")
def update_member(member_id: int, group_member_data: GroupMembersCreateEdit, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    member = db.query(GroupMember).get(member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.name = group_member_data.get("name")
    db.commit()
    return member

@router.delete("/{member_id}")
def delete_member(member_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    member = db.query(GroupMember).get(member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    db.commit()
    return {"message": "Member deleted"}
