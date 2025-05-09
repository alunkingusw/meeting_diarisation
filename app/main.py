from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from datetime import timedelta
from datetime import datetime
from pathlib import Path
import shutil

#from app.processing import process_audio

UPLOAD_DIR = Path("app/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()

# Record start time for uptime
start_time = datetime.now

def check_model_status():
    # Placeholder: change this to check real model state later
    whisper_ready = os.path.exists("some_model_file_or_flag.txt")
    llama_ready = True  # Replace with real health check logic

    return {
        "whisper_model": "available" if whisper_ready else "unavailable",
        "llama_model": "available" if llama_ready else "unavailable"
    }

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Trigger processing (placeholder)
    result = process_audio(file_path)

    return JSONResponse(content={"message": "File uploaded", "result": result})

@app.get("/status")
def get_status():
    uptime = datetime.now - start_time
    models = check_model_status()
    
    return {
        "status": "ok",
        "uptime": str(timedelta(seconds=int(uptime.total_seconds()))),
        "models": models
    }
