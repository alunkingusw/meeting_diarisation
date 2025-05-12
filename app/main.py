from fastapi import FastAPI
from fastapi.responses import JSONResponse
from datetime import timedelta, timezone, datetime
from pathlib import Path
from app.routes import router as api_router
from app.startup import set_start_time, set_upload_folder

from app.processing import process_audio



app = FastAPI()

@app.on_event("startup")
def startup_event():
    set_start_time()
    set_upload_folder()

app.include_router(api_router)




