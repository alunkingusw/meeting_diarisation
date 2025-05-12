from sqlalchemy import Column, Integer, String, DateTime
from app.db import Base
from datetime import datetime

class AudioFile(Base):
    __tablename__ = "audio_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    path = Column(String)
    uploaded_at = Column(DateTime, default=datetime.now().astimezone())
