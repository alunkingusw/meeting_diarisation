# NOTE - if this file is altered and it affects the database schema, 
# run this command in the terminal
# python -m alembic revision --autogenerate -m "Describe your changes here"
# then apply to the database using the following command
# python -m alembic upgrade head
from pydantic import BaseModel, field_validator
from typing import List, Optional
from datetime import datetime
from backend.config import settings

from enum import Enum

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Table, JSON, func, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from backend.db import Base

# Association Tables

users_groups = Table(
    "users_groups", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id"), primary_key=True)
)

groups_group_members = Table(
    "groups_group_members", Base.metadata,
    Column("group_id", Integer, ForeignKey("groups.id"), primary_key=True),
    Column("group_member_id", Integer, ForeignKey("group_members.id"), primary_key=True)
)

meetings_group_members = Table(
    "meetings_group_members", Base.metadata,
    Column("meeting_id", Integer, ForeignKey("meetings.id"), primary_key=True),
    Column("group_member_id", Integer, ForeignKey("group_members.id"), primary_key=True),
    Column("confirmed", Boolean, default=False)
)

# Tables

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(255), nullable=True)
    created = Column(DateTime, nullable=False, default=func.now())

    groups = relationship("Group", secondary=users_groups, back_populates="users")


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=True)
    created = Column(DateTime, nullable=False, default=func.now())

    users = relationship("User", secondary=users_groups, back_populates="groups")
    members = relationship("GroupMember", secondary=groups_group_members, back_populates="groups")
    meetings = relationship("Meeting", back_populates="group")


class GroupMember(Base):
    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=True)
    created = Column(DateTime, nullable=False, default=func.now())

    embedding = Column(JSON, nullable=True)  # Stores list of floats from pyannote
    embedding_audio_path = Column(String(255), nullable=True)  # Optional: for reference/debugging
    embedding_updated_at = Column(DateTime, nullable=True)

    groups = relationship("Group", secondary=groups_group_members, back_populates="members")
    attended_meetings = relationship("Meeting", secondary=meetings_group_members, back_populates="attendees")

class Meeting(Base):
    __tablename__ = "meetings"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    date = Column(DateTime, nullable=False, default=func.now())
    created = Column(DateTime, nullable=False, default=func.now())

    group = relationship("Group", back_populates="meetings")
    attendees = relationship("GroupMember", secondary=meetings_group_members, back_populates="attended_meetings")
    media_files = relationship("RawFile", back_populates="meeting", cascade="all, delete-orphan")



class RawFileType(str, Enum):
    AUDIO = "audio"
    TRANSCRIPT_PROVIDED = "transcript_provided"
    TRANSCRIPT_GENERATED = "transcript_generated"


class RawFile(Base):
    __tablename__ = "raw_files"
    id = Column(Integer, primary_key=True)
    file_name = Column(String(255), nullable=True)
    human_name = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"),nullable=False)
    processed_date = Column(DateTime, nullable=True)
    type = Column(SQLEnum(RawFileType, name="raw_file_type"), nullable=False)
    meeting=relationship("Meeting", back_populates="media_files")
    status=Column(Text, nullable=True)

class GroupMemberOut(BaseModel):
    id: int
    name: str
    created: datetime
    embedding_audio_path: Optional[str]
    @field_validator("embedding_audio_path", mode="before")
    def add_base_url(cls, v):
        if v and not v.startswith("http"):
            return f"{settings.EMBEDDING_DIR}{v}"
        return v
    
    class Config:
        from_attributes = True

class GroupOut(BaseModel):
    id: int
    name: str
    created: datetime
    members: List[GroupMemberOut]  # Include related members
    class Config:
        from_attributes = True

class RawFileCreate(BaseModel):
    file_name: str
    human_name: str
    description: Optional[str]
    type: RawFileType
    meeting_id: int

class RawFileCreate(BaseModel):
    file_name: str
    human_name: str
    description: Optional[str]
    type: RawFileType
    meeting_id: int

class RawFileOut(BaseModel):
    id: int
    human_name:str
    file_name:str
    description:Optional[str]
    processed_date:Optional[datetime]
    type:RawFileType
    class Config:
        from_attributes =True

class MeetingAttendeeOut(BaseModel):
    id: int
    name: str
    created: datetime

    class Config:
        from_attributes  = True

class MeetingOut(BaseModel):
    id:int
    group_id:int
    date:datetime
    created:datetime
    attendees: List[MeetingAttendeeOut]  # Include all attendees
    media_files: List[RawFileOut]
    class Config:
        from_attributes  = True