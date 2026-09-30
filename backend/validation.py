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

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
import bleach
from datetime import datetime

#define the required and optional fields that accompany a file upload. Specify default values.
class FileUploadMetadata(BaseModel):
    description: str = Field(min_length=5)
    speaker_hint: Optional[int] = Field(None, ge=1, le=10, example=3)
    language: Optional[str] = Field("en", example="en")

class ServiceUserTokenRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("email must be a valid email address")
        return value

class GroupCreateEdit(BaseModel):
    name: str
    github_repo_url: Optional[str] = None
    trello_board_id: Optional[str] = None
    notify: bool = False
    # Only honoured for administrators (backend/routes/groups.py) - lets an admin create a
    # group owned by another user instead of themselves. Ignored/rejected for everyone else.
    owner_user_id: Optional[int] = None

class MeetingCreateEdit(BaseModel):
    date: datetime

class MeetingCommentCreate(BaseModel):
    comment: str = Field(min_length=1, max_length=10000)

    @field_validator("comment")
    @classmethod
    def sanitise_comment(cls, value: str) -> str:
        cleaned = bleach.clean(value, tags=[], attributes={}, strip=True)
        cleaned = cleaned.strip()
        if not cleaned:
            raise ValueError("Comment must contain text")
        return cleaned

class UserCreateEdit(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    # Optional - most users only interact with the system via email (e.g. GroupAssessmentAgent
    # issuing them a JWT through /admin/user-token), so a login password isn't always needed.
    password: Optional[str] = Field(None, min_length=12, max_length=1024)
    email: Optional[str] = Field(None, max_length=255)
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def normalise_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("username cannot be blank")
        return value.lower()


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=1, max_length=255)
    password: Optional[str] = Field(None, min_length=12, max_length=1024)
    email: Optional[str] = Field(None, max_length=255)
    is_admin: Optional[bool] = None

    @field_validator("username")
    @classmethod
    def normalise_username(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("username cannot be blank")
        return value.lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: Optional[str]
    email: Optional[str]
    is_admin: bool
    created: datetime

class GroupMembersCreateEdit(BaseModel):
    name: str
    email: Optional[str] = None

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip().lower()
        if not value:
            return None
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("email must be a valid email address")
        return value

class MeetingAttendee(BaseModel):
    name: Optional[str] = None
    guest: Optional[int] = 0
    member_id: Optional[int] = None

class AliasResolveRequest(BaseModel):
    names: List[str]
    source: Optional[str] = None