from datetime import timedelta, timezone, datetime
from pathlib import Path
# Record start time for uptime
START_TIME = None
UPLOAD_DIR = None

def set_start_time():
    global START_TIME
    START_TIME = datetime.now().astimezone()

def set_upload_folder():
    global UPLOAD_DIR
    UPLOAD_DIR = Path("app/uploads")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def set_database_name():
    global MONGO_URL
    global MONGO_DB_NAME
    MONGO_URL = "mongodb://localhost:27017"
    MONGO_DB_NAME = "diarisation_db"
