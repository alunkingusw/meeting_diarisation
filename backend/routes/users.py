# backend/routers/users.py

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

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from sqlalchemy.orm import Session

from backend.models import User
from backend.db_dependency import get_db
from backend.auth import create_token_for_user
from backend.validation import LoginRequest
from backend.validation import UserCreateEdit

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/login")
async def generate_token(
    username: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        user_id = int(username)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    # validate user exists in DB:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_token_for_user(user_id)
    return {
        "access_token": token,
        "token_type": "bearer"
    }
@router.post("/")
def create_user(user_data:UserCreateEdit, db: Session = Depends(get_db)):
    user = User(username=user_data.get.username)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.get("/")
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@router.get("/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/{user_id}")
def update_user(user_data:UserCreateEdit, username: str, db: Session = Depends(get_db)):
    user = db.query(User).get(user_data.get.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.username = user_data.get("username")
    db.commit()
    return user

@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}
