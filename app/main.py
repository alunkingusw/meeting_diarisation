from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.routes import router as api_router

import app.startup


from app.processing import process_audio

app = FastAPI()

#create default landing page for quick checks.
@app.get("/")
def root():
    return {"message": "Diarisation API is running."}

app.include_router(api_router)