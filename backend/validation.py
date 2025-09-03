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

from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime

#define the required and optional fields that accompany a file upload. Specify default values.
class FileUploadMetadata(BaseModel):
    description: str = Field(min_length=5)
    speaker_hint: Optional[int] = Field(None, ge=1, le=10, example=3)
    language: Optional[str] = Field("en", example="en")

class LoginRequest(BaseModel):
    username: str

class GroupCreateEdit(BaseModel):
    name: str

class MeetingCreateEdit(BaseModel):
    date: datetime

class UserCreateEdit(BaseModel):
    username: str

class GroupMembersCreateEdit(BaseModel):
    name: str

class MeetingAttendee(BaseModel):
    name: Optional[str] = None
    guest: Optional[int] = 0
    member_id: Optional[int] = None