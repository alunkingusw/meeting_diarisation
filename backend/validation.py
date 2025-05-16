from typing import Optional
from pydantic import BaseModel, Field

#define the required and optional fields that accompany a file upload. Specify default values.
class FileUploadMetadata(BaseModel):
    description: str = Field(min_length=5)
    speaker_hint: Optional[int] = Field(None, ge=1, le=10, example=3)
    language: Optional[str] = Field("en", example="en")

class LoginRequest(BaseModel):
    user_id: int

class GroupCreateEdit(BaseModel):
    name: str

class MeetingCreateEdit(BaseModel):
    groups_idgroups: int

class UserCreateEdit(BaseModel):
    username: str

class GroupMembersCreateEdit(BaseModel):
    name: str