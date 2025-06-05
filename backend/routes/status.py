from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from datetime import datetime
import os

from backend.db import SessionLocal
from backend.startup import START_TIME

router = APIRouter()
HUGGING_FACE_TOKEN = os.getenv("HUGGING_FACE_TOKEN")

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
    status = {}

    # Whisper check
    try:
        import whisper
        model = whisper.load_model("base")
        status["whisper_model"] = {
            "status": "available",
            "version": whisper.__version__ if hasattr(whisper, "__version__") else "unknown"
        }
    except Exception as e:
        status["whisper_model"] = {
            "status": f"unavailable ({str(e)})",
            "version": "unknown"
        }

    # PyAnnote check
    try:
        from pyannote.audio import Pipeline
        import pyannote
        Pipeline.from_pretrained("pyannote/speaker-diarization", use_auth_token=HUGGING_FACE_TOKEN)
        status["pyannote_diarization"] = {
            "status": "available",
            "version": pyannote.__version__ if hasattr(pyannote, "__version__") else "unknown"
        }
    except Exception as e:
        status["pyannote_diarization"] = {
            "status": f"unavailable ({str(e)})",
            "version": "unknown"
        }

    # Resemblyzer check
    try:
        from resemblyzer import VoiceEncoder
        import resemblyzer
        VoiceEncoder()
        version = getattr(resemblyzer, '__version__', 'unknown')
        status["resemblyzer_voice_encoder"] = {
            "status": "available",
            "version": version
        }
    except Exception as e:
        status["resemblyzer_voice_encoder"] = {
            "status": f"unavailable ({str(e)})",
            "version": "unknown"
        }

    return status
