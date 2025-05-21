# backend/routers/meetings.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import Meeting, Group
from backend.db_dependency import get_db
from datetime import datetime
from backend.validation import MeetingCreateEdit
from backend.auth import get_current_user_id, is_group_user

router = APIRouter(prefix="/groups/{group_id}/meetings", tags=["meetings"])

@router.post("/")
def create_meeting(
        group_id: int,
        meeting_data:MeetingCreateEdit,
        db: Session = Depends(get_db), 
        user_id: int = Depends(is_group_user)
    ):
    new_meeting = Meeting(group_id=group_id, date=meeting_data.date, created=datetime.now())
    
    db.add(new_meeting)
    db.commit()
    db.refresh(new_meeting)
    return new_meeting

@router.get("/")
def list_meetings(
        group_id: int,
        db: Session = Depends(get_db), 
        user_id: int = Depends(is_group_user)
    ):
    return db.query(Meeting).filter(Meeting.group_id == group_id).all()

@router.get("/{meeting_id}")
def get_meeting(
        group_id: int,
        meeting_id: int, 
        db: Session = Depends(get_db), 
        user_id: int = Depends(is_group_user)
    ):
    meeting = db.query(Meeting).filter(Meeting.idmeetings == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting

@router.delete("/{meeting_id}")
def delete_meeting(
        group_id: int,
        meeting_id: int,
        db: Session = Depends(get_db),
        user_id: int = Depends(is_group_user)
    ):
    meeting = db.query(Meeting).filter(Meeting.idmeetings == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    db.delete(meeting)
    db.commit()
    return {"message": "Meeting deleted"}
