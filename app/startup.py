from datetime import datetime
from pathlib import Path
# Record start time for uptime
START_TIME = datetime.now().astimezone()

#start database
from app.db import Base, engine
from app.models import RawFiles

Base.metadata.create_all(bind=engine)

UPLOAD_DIR = Path("app/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
