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

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, exists
from backend.config import settings
from backend.models import RawFile, RawFileType, GroupMember, User, Group
from werkzeug.utils import secure_filename
from backend.db_dependency import get_db
from backend.auth import get_current_user_id
from fastapi.responses import FileResponse
import uuid
import os
import re



import shutil
#from backend.processing import transcribe

router = APIRouter()

# Allowed file extensions
ALLOWED_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.m4a'}
ALLOWED_TRANSCRIPT_EXTENSIONS = {'.json', '.vtt', '.srt', '.txt'}
ALL_ALLOWED_EXTENSIONS = ALLOWED_AUDIO_EXTENSIONS | ALLOWED_TRANSCRIPT_EXTENSIONS
FILENAME_RE = re.compile(r"^[\w.\-]+$")  # Allows: a-zA-Z0-9 _ . -

def validate_filename(filename: str) -> str:
    if not FILENAME_RE.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename

@router.post("/groups/{group_id}/meetings/{meeting_id}/upload/", tags=["meetings"])
async def upload_file(
        group_id:int,
        meeting_id:int,
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        user_id: int = Depends(get_current_user_id)
    ):
    # Extract extension and validate
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALL_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: '{ext}'. Allowed types: {', '.join(sorted(ALL_ALLOWED_EXTENSIONS))}"
        )
    
    # if it's not an audio file, then it's a provided transcript
    file_type=RawFileType.TRANSCRIPT_PROVIDED
    if ext in ALLOWED_AUDIO_EXTENSIONS:
        file_type=RawFileType.AUDIO
    
    human_filename = secure_filename(file.filename)
    safe_filename = f"{uuid.uuid4().hex}_{human_filename}"
    
    # Build target directory path: uploads/group_id/meeting_id
    target_dir = settings.UPLOAD_DIR / str(group_id) / str(meeting_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / safe_filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # add file upload to the database. Leave processed as null as it has not yet been looked at.
    
    raw_file = RawFile(
        file_name=safe_filename,
        human_name=human_filename,
        description=None,
        meeting_id = meeting_id,
        type=file_type,
    )
    db.add(raw_file)
    db.commit()
    db.refresh(raw_file)
    return raw_file

    # Trigger processing (placeholder)
    # result = process_audio(file_path)
@router.get("/files/media/{group_id}/{meeting_id}/{filename}")
def serve_media(
        group_id:int,
        meeting_id:int,
        filename:str = Depends(validate_filename),
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
    ):

    if not user_can_access_group(db, user_id, group_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    file_path = os.path.join(settings.UPLOAD_DIR, str(group_id), str(meeting_id), filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found: "+file_path)
    
    response = FileResponse(file_path)
    return response
    
@router.get("/files/embedding/{filename}")
def serve_file(
        filename: str = Depends(validate_filename), 
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
    ):

    if not user_can_access_embedding(db, user_id, filename):
        raise HTTPException(status_code=403, detail="Forbidden")
    file_path = os.path.join(settings.EMBEDDING_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found: "+file_path)
    
    response = FileResponse(file_path)
    return response

def user_can_access_embedding(db: Session, user_id: int, filename: str) -> bool:
    # Find the GroupMember(s) that own this file
    member = db.query(GroupMember).filter(GroupMember.embedding_audio_path == filename).first()
    if not member:
        return False

    # Get groups of the member
    member_group_ids = [group.id for group in member.groups]

    # Get groups of the user
    user_group_ids = (
        db.query(User)
        .filter(User.id == user_id)
        .join(User.groups)
        .with_entities(Group.id)
        .all()
    )
    user_group_ids = [g[0] for g in user_group_ids]

    # Check if any group overlaps
    return any(gid in user_group_ids for gid in member_group_ids)

def user_can_access_group(db: Session, user_id: int, group_id: int) -> bool:
    return db.query(
        exists().where(
            Group.id == group_id,
            Group.users.any(User.id == user_id)
        )
    ).scalar()

