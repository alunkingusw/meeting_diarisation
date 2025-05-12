from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.startup import UPLOAD_DIR
from app.models import AudioFile
from werkzeug.utils import secure_filename

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

import shutil
from app.processing import process_audio

router = APIRouter()


@router.post("/upload/")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    safe_filename = secure_filename(file.filename)
    file_path = UPLOAD_DIR / safe_filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # add file upload to the database
    
    audio = AudioFile(filename=safe_filename, path=file_path)
    db.add(audio)
    db.commit()
    db.refresh(audio)
    return {"message": "File uploaded", "id": audio.id}

    # Trigger processing (placeholder)
    # result = process_audio(file_path)
