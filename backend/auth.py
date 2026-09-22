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

#use this file to check auth tokens when user uploads work.
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import HTTPException, Depends, Path, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.db_dependency import get_db
from backend.models import Group, users_groups
import os
import secrets

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")  # This URL is for OpenAPI docs only

# Secret key for signing the JWT — keep this secure!
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # Token expires after 1 hour

# Separate from the per-user JWT flow above: a shared secret for trusted backend-to-backend
# callers (e.g. GroupAssessmentAgent) that need read access to admin data without impersonating
# a specific user. Checked via the X-Service-Key header, never Authorization, so the two
# credential types can never be confused with or accepted in place of one another.
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY")

def create_token_for_user(user_id: int) -> str:
    expire = datetime.now().astimezone() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id), "exp": expire}
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return int(user_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _group_role(db: Session, user_id: int, group_id: int) -> str | None:
    return db.execute(
        users_groups.select()
        .with_only_columns(users_groups.c.role)
        .where(
            users_groups.c.user_id == user_id,
            users_groups.c.group_id == group_id,
        )
    ).scalar_one_or_none()


def is_group_member(
    group_id: int = Path(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> int:
    if not db.query(Group).filter(Group.id == group_id).first():
        raise HTTPException(status_code=404, detail="Group not found")

    role = get_group_role(db, user_id, group_id)
    if role not in {"owner", "member"}:
        raise HTTPException(status_code=403, detail="Not authorised to view this group")

    return user_id


def get_group_role(db: Session, user_id: int, group_id: int) -> str | None:
    return _group_role(db, user_id, group_id)


def is_group_owner(
    group_id: int = Path(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
) -> int:
    if not db.query(Group).filter(Group.id == group_id).first():
        raise HTTPException(status_code=404, detail="Group not found")

    if _group_role(db, user_id, group_id) != "owner":
        raise HTTPException(status_code=403, detail="Group owner permission required")

    return user_id


# Existing routes can continue to use this name while they are migrated to explicit roles.
is_group_user = is_group_member


def get_service_caller(x_service_key: str = Header(default=None)) -> None:
    """Gate for trusted service-to-service endpoints (backend/routes/admin.py). Requires
    SERVICE_API_KEY to be set - if it isn't, every call is rejected rather than left open."""
    if not SERVICE_API_KEY or not x_service_key or not secrets.compare_digest(x_service_key, SERVICE_API_KEY):
        raise HTTPException(status_code=401, detail="Missing or invalid service key")