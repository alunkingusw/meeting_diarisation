from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Table, func
)
from sqlalchemy.orm import relationship
from app.db import Base

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
    username = Column(String(45), nullable=True)
    created = Column(DateTime, nullable=False, default=func.now())

    groups = relationship("Group", secondary=users_groups, back_populates="users")


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True)
    name = Column(String(45), nullable=True)
    created = Column(DateTime, nullable=False, default=func.now())

    users = relationship("User", secondary=users_groups, back_populates="groups")
    members = relationship("GroupMember", secondary=groups_group_members, back_populates="groups")
    meetings = relationship("Meeting", back_populates="group")


class GroupMember(Base):
    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True)
    name = Column(String(45), nullable=True)
    created = Column(DateTime, nullable=False, default=func.now())

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

class RawFile(Base):
    __tablename__ = "raw_files"
    id = Column(Integer, primary_key=True)
    file_name = Column(String(45), nullable=True)
    human_name = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"),nullable=False)
    meeting=relationship("Meeting", back_populates="media_files")
    