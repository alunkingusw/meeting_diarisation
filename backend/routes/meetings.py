# backend/routers/meetings.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import and_
from sqlalchemy.orm import Session
from backend.models import Meeting, MeetingOut, GroupMember, RawFile
from backend.db_dependency import get_db
from datetime import datetime
from backend.validation import MeetingCreateEdit, MeetingAttendee
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

@router.get("/{meeting_id}", response_model=MeetingOut)
def get_meeting(
        group_id: int,
        meeting_id: int, 
        db: Session = Depends(get_db), 
        user_id: int = Depends(is_group_user)
    ):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
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
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    db.delete(meeting)
    db.commit()
    return {"message": "Meeting deleted"}

@router.post("/{meeting_id}/attendees")
def add_attendee(
        group_id:int,
        meeting_id:int,
        attendee_data:MeetingAttendee,
        db:Session = Depends(get_db),
        user_id: int = Depends(is_group_user)
    ):
    print("Recieved attendee data:", attendee_data)
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    #if the member exists, then add them to the attendance.
    if attendee_data.member_id:
        # Add existing member to the meeting
        member = db.query(GroupMember).filter(GroupMember.id == attendee_data.member_id).first()
        if not member:
            raise HTTPException(status_code=404, detail="Member not found")

    elif attendee_data.guest and attendee_data.name:
        # Create a new guest group member
        member = GroupMember(name=attendee_data.name)
        db.add(member)
        db.commit()
        db.refresh(member)
    else:
        raise HTTPException(status_code=400, detail="Invalid attendee data")

    # Link the member to the meeting
    if member not in meeting.attendees:
        meeting.attendees.append(member)
        db.commit()

    return member

@router.delete("/{meeting_id}/attendees/{member_id}")
def remove_attendee(
    group_id: int,
    meeting_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_user)
):
    # Check if meeting exists
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Check if member exists
    member = db.query(GroupMember).filter(GroupMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Remove the member from the meeting attendees
    if member in meeting.attendees:
        meeting.attendees.remove(member)
        db.commit()
        return {"message": "Attendee removed"}
    else:
        raise HTTPException(status_code=404, detail="Member is not an attendee of this meeting")
    
@router.post("/{meeting_id}/transcribe")
async def start_transcription_job(
    group_id: int,
    meeting_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(is_group_user),
    background_tasks: BackgroundTasks = None
):
    # Check if there's at least one audio file uploaded for this meeting
    audio_file = db.query(RawFile).filter(
        and_(
            RawFile.meeting_id == meeting_id,
            RawFile.type == "audio"
        )
    ).first()

    if not audio_file:
        raise HTTPException(
            status_code=400,
            detail="No audio files found for this meeting. Please upload an audio file before starting transcription."
        )

    # STUB: Kick off transcription (e.g., background task or job queue)
    # Example: background_tasks.add_task(process_audio, audio_file.file_name)
    # Replace with actual logic, e.g., pass file path, IDs, etc.
    print(f"Stub: Would kick off transcription for file {audio_file.file_name}")

    return {
        "message": "Transcription job started.",
        "file": audio_file.file_name,
        "status_check_url": f"/groups/{group_id}/meetings/{meeting_id}/transcription/status"
    }