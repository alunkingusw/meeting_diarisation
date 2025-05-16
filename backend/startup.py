from datetime import datetime
from pathlib import Path
from backend import models
from backend.db import Base, engine

import logging

logging.basicConfig(level=logging.INFO)
logging.info("Starting application...")

# Record start time for uptime
START_TIME = datetime.now().astimezone()
logging.info(f"App start time: {START_TIME}")



logging.info("Creating database tables (if not exist)...")


#start database
try:
    Base.metadata.create_all(bind=engine)
    logging.info("Database tables created successfully.")
except Exception as e:
    logging.error(f"Error initializing the database: {e}")

UPLOAD_DIR = Path("backend/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
