from fastapi import APIRouter, UploadFile, File
from datetime import datetime
from pathlib import Path
from app.db import db

import shutil
from app.processing import process_audio

router = APIRouter()

UPLOAD_DIR = Path("app/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # add file upload to the database
    #db.audio_files.insert_one({
    #    "filename": file.filename,
    #    "uploaded_at": datetime.now().astimezone(),
    #    "path": file_path,
    #})

    # Trigger processing (placeholder)
    result = process_audio(file_path)

    return {"message": "File uploaded", "result": result}