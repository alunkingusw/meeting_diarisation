from fastapi import FastAPI
from fastapi.responses import JSONResponse
from backend.routes import router as api_router

import backend.startup
import logging

logging.basicConfig(level=logging.INFO)

#from backend.processing import process_audio
from fastapi.middleware.cors import CORSMiddleware

backend = FastAPI()

#add middleware for communication between backend and frontend running on the same server
origins = [
    "http://localhost:3000",
    "http://frontend:3000",  # Docker internal hostname
]

backend.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#create default landing page for quick checks.
@backend.get("/")
def root():
    return {"message": "Diarisation API is running."}


backend.include_router(api_router)
#logging.info("Middleware stack: %s", backend.user_middleware)