from fastapi import FastAPI
from fastapi.responses import JSONResponse
from datetime import timedelta, timezone, datetime
from pathlib import Path
from app.routes import router as api_router


from app.processing import process_audio

app = FastAPI()

app.include_router(api_router)