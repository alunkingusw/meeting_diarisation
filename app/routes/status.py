from fastapi import APIRouter
from datetime import datetime
from app.startup import START_TIME
import os

router = APIRouter()

@router.get("/status")
def get_status():
    uptime = datetime.now().astimezone() - START_TIME if START_TIME else "Unknown"
    models = check_model_status()
    return {
        "status": "ok",
        "uptime": str(uptime),
        "models": models
    }

def check_model_status():
    # Placeholder: change this to check real model state later
    whisper_ready = os.path.exists("some_model_file_or_flag.txt")
    llama_ready = True  # Replace with real health check logic

    return {
        "whisper_model": "available" if whisper_ready else "unavailable",
        "llama_model": "available" if llama_ready else "unavailable"
    }
