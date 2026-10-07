# Copyright 2025 Alun King
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
    Column, Integer, String, Text, DateTime, Date, Boolean, ForeignKey, Table, JSON, Index, func, text,
    Enum as SQLEnum,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from backend.db import Base

# Association Tables

# supervisor ownership of groups, so they can manage group members and meetings
users_groups = Table(
    "users_groups", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id"), primary_key=True),
    Column("role", String(20), nullable=False, server_default="owner")
)

#regular group members who are part of the group and can be invited to meetings
groups_group_members = Table(
    "groups_group_members", Base.metadata,
    Column("group_id", Integer, ForeignKey("groups.id"), primary_key=True),
    Column("group_member_id", Integer, ForeignKey("group_members.id"), primary_key=True)
)

#for when there is a one off guest in the meeting.
meetings_group_members = Table(
    "meetings_group_members", Base.metadata,
    Column("meeting_id", Integer, ForeignKey("meetings.id"), primary_key=True),
    Column("group_member_id", Integer, ForeignKey("group_members.id"), primary_key=True),
    Column("confirmed", Boolean, default=False)
)

# Tables

#a user is a supervisor who can manage groups
class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_username_lower",
            text("lower(username)"),
            unique=True,
            postgresql_where=text("username IS NOT NULL"),
        ),
    )
    id = Column(Integer, primary_key=True)
    username = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)
    is_admin = Column(Boolean, nullable=False, default=False, server_default="false")
    created = Column(DateTime, nullable=False, default=func.now())

    groups = relationship("Group", secondary=users_groups, back_populates="users")


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=True)
    # A 1:1 GitHub repo / Trello board mapping, so meeting_diarisation stays the single source
    # of truth for group/project-organisation data - GitHub-RAGinator's own repo registration
    # is synced from this (see GitHub-RAGinator/scripts/sync_repos_from_diarisation.py), not
    # maintained separately.
    github_repo_url = Column(String(512), nullable=True)
    trello_board_id = Column(String(24), nullable=True)
    notify = Column(Boolean, nullable=False, default=False)
    created = Column(DateTime, nullable=False, default=func.now())

    users = relationship("User", secondary=users_groups, back_populates="groups")
    members = relationship("GroupMember", secondary=groups_group_members, back_populates="groups")
    meetings = relationship("Meeting", back_populates="group")

#group members are the students or other participants who are part of the group and can be invited to meetings
class GroupMember(Base):
    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)  # optional, but can be used to send updates to the group member
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
    idempotency_key = Column(String(255), nullable=True, unique=True, index=True)
    date = Column(DateTime, nullable=False, default=func.now())
    created = Column(DateTime, nullable=False, default=func.now())

    group = relationship("Group", back_populates="meetings")
    attendees = relationship("GroupMember", secondary=meetings_group_members, back_populates="attended_meetings")
    media_files = relationship("RawFile", back_populates="meeting", cascade="all, delete-orphan")
    comments = relationship("MeetingComment", back_populates="meeting", cascade="all, delete-orphan")

    # LLM-generated summary (backend/summarization), cached here so a meeting is only
    # summarised once - GET /groups/{group_id}/meetings/{meeting_id}/summarise serves this
    # if present rather than calling the local LLM again.
    summary = Column(Text, nullable=True)
    summary_generated_at = Column(DateTime, nullable=True)


class MeetingComment(Base):
    __tablename__ = "meeting_comments"
    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    group_member_id = Column(Integer, ForeignKey("group_members.id"), nullable=True)
    comment = Column(Text, nullable=False)
    created = Column(DateTime, nullable=False, default=func.now())

    meeting = relationship("Meeting", back_populates="comments")
    user = relationship("User")
    group_member = relationship("GroupMember")



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

class Job(Base):
    """A long-running piece of work (see backend/jobs). State lives here so any API client can poll it."""

    __tablename__ = "jobs"
    id = Column(String(36), primary_key=True)
    kind = Column(String(40), nullable=False, index=True)
    state = Column(String(20), nullable=False, default="queued", index=True)
    # Who asked for it: a user, or a group member who emailed a transcript in.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    group_member_id = Column(Integer, ForeignKey("group_members.id"), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=True, index=True)
    params = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=True)
    progress = Column(String(255), nullable=True)
    error = Column(Text, nullable=True)
    error_type = Column(String(80), nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class WeeklyReport(Base):
    """Backend-owned report snapshot used for scheduled delivery and email follow-ups."""

    __tablename__ = "weekly_reports"
    __table_args__ = (
        UniqueConstraint("group_id", "period_start", "period_end", name="uq_weekly_report_period"),
    )

    report_id = Column(String(64), primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False, index=True)
    group_name = Column(String(255), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    report_text = Column(Text, nullable=True)
    model = Column(String(255), nullable=True)
    evidence = Column(JSON, nullable=True)
    unavailable = Column(JSON, nullable=False, default=list)
    recipients = Column(JSON, nullable=False, default=list)
    queued_recipients = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())


class GroupMemberOut(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    created: datetime
    embedding_audio_path: Optional[str]
    
    class Config:
        from_attributes = True

class GroupOut(BaseModel):
    id: int
    name: str
    created: datetime
    github_repo_url: Optional[str] = None
    trello_board_id: Optional[str] = None
    github_connected: bool = False
    trello_connected: bool = False
    notify: bool = False
    members: List[GroupMemberOut]  # Include related members
    class Config:
        from_attributes = True

class RawFileOut(BaseModel):
    id: int
    human_name:str
    file_name:str
    description:Optional[str]
    processed_date:Optional[datetime]
    type:RawFileType
    # Set for a transcript upload: poll GET /jobs/{id} for indexing and summarising.
    processing_job_id: Optional[str] = None
    class Config:
        from_attributes =True

class MeetingAttendeeOut(BaseModel):
    id: int
    name: str
    created: datetime

    class Config:
        from_attributes  = True

class MeetingCommentOut(BaseModel):
    id: int
    meeting_id: int
    user_id: Optional[int] = None
    group_member_id: Optional[int] = None
    comment: str
    created: datetime

    class Config:
        from_attributes = True

class MeetingOut(BaseModel):
    id:int
    group_id:int
    date:datetime
    created:datetime
    attendees: List[MeetingAttendeeOut]  # Include all attendees
    media_files: List[RawFileOut]
    comments: List[MeetingCommentOut]
    summary: Optional[str] = None
    summary_generated_at: Optional[datetime] = None
    class Config:
        from_attributes  = True