from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session
from backend.startup import UPLOAD_DIR
from backend.models import RawFile
from werkzeug.utils import secure_filename
from backend.db_dependency import get_db
from backend.auth import get_current_user_id
import uuid



import shutil
from backend.processing import process_audio

router = APIRouter()


@router.post("/groups/{group_id}/meetings/{meeting_id}/upload/")
async def upload_file(
        group_id:int,
        meeting_id:int,
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        user_id: int = Depends(get_current_user_id)
    ):
    human_filename = secure_filename(file.filename)
    safe_filename = f"{uuid.uuid4().hex}_{human_filename}"
    
    # Build target directory path: uploads/group_id/meeting_id
    target_dir = UPLOAD_DIR / str(group_id) / str(meeting_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / safe_filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # add file upload to the database
    
    raw_file = RawFile(
        file_name=safe_filename,
        human_name=human_filename,
        description=None,
        meeting_id = meeting_id,
    )
    db.add(raw_file)
    db.commit()
    db.refresh(raw_file)
    return raw_file

    # Trigger processing (placeholder)
    # result = process_audio(file_path)
