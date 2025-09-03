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
from fastapi import HTTPException, Depends, Path
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.db_dependency import get_db
from backend.models import Group
import os

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")  # This URL is for OpenAPI docs only

# Secret key for signing the JWT — keep this secure!
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # Token expires after 1 hour

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


def is_group_user(
    group_id: int = Path(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
) -> int:
    group = db.query(Group).get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if user_id not in [user.id for user in group.users]:
        raise HTTPException(status_code=403, detail="Not authorised to view this group")

    return user_id  # You can return group if you prefer!