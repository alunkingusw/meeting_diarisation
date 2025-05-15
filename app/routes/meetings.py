# app/routers/meetings.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models import Meeting
from app.db_dependency import get_db
from datetime import datetime

router = APIRouter(prefix="/meetings", tags=["meetings"])

@router.post("/")
def create_meeting(groups_idgroups: int, db: Session = Depends(get_db)):
    meeting = Meeting(groups_idgroups=groups_idgroups, date=datetime.now(), created=datetime.now())
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting

@router.get("/")
def list_meetings(db: Session = Depends(get_db)):
    return db.query(Meeting).all()

@router.get("/{meeting_id}")
def get_meeting(meeting_id: int, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.idmeetings == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting

@router.delete("/{meeting_id}")
def delete_meeting(meeting_id: int, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.idmeetings == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    db.delete(meeting)
    db.commit()
    return {"message": "Meeting deleted"}
