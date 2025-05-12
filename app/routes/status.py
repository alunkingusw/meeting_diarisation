from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from datetime import datetime
import os

from app.db import SessionLocal
from app.startup import START_TIME

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    uptime = datetime.now().astimezone() - START_TIME if START_TIME else "Unknown"
    models = check_model_status()

    # Check PostgreSQL connection
    try:
        db.execute(text('SELECT 1'))  # Lightweight DB health check
        db_status = "connected"
    except SQLAlchemyError as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "ok",
        "uptime": str(uptime),
        "models": models,
        "database": db_status
    }

def check_model_status():
    # Placeholder: change this to check real model state later
    whisper_ready = os.path.exists("some_model_file_or_flag.txt")
    llama_ready = True  # Replace with real health check logic

    return {
        "whisper_model": "available" if whisper_ready else "unavailable",
        "llama_model": "available" if llama_ready else "unavailable"
    }
