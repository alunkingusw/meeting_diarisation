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

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash
from pathlib import Path
from string import Template

from backend.models import User
from backend.db_dependency import get_db
from backend.auth import create_token_for_user, get_current_user_id, get_current_admin_id
from backend.validation import UserCreateEdit, UserOut, UserUpdate
from backend.email_client import EmailError, send_email

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

WELCOME_EMAIL_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "user_welcome_email.txt"


def _render_welcome_email(user: User) -> tuple[str, str]:
    template_lines = WELCOME_EMAIL_TEMPLATE_PATH.read_text(encoding="utf-8").splitlines()
    template_text = "\n".join(line for line in template_lines if not line.startswith("#"))
    admin_note = (
        "- As an administrator, you can also add other users and create groups on their behalf.\n"
        if user.is_admin
        else ""
    )
    body = Template(template_text).substitute(
        username=user.username or "there",
        admin_note=admin_note,
    )
    subject = "Welcome to the Meeting Diarisation system"
    return subject, body.strip()


def _send_welcome_email(user: User) -> None:
    if not user.email:
        logger.info("Notify requested for user %s but no email address is set", user.id)
        return
    try:
        subject, body = _render_welcome_email(user)
        send_email(to=user.email.strip(), subject=subject, body=body)
    except EmailError:
        logger.exception("Could not send welcome email to user %s", user.id)

@router.post("/login")
def generate_token(
    credentials: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == credentials.username.strip().lower()).first()
    if not user or not user.password_hash or not check_password_hash(user.password_hash, credentials.password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_token_for_user(user.id)
    return {
        "access_token": token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=UserOut)
def get_current_user(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=UserOut, status_code=201)
def create_user(
    user_data: UserCreateEdit,
    background_tasks: BackgroundTasks,
    notify: bool = Query(True, description="Send the user a welcome email once added"),
    db: Session = Depends(get_db),
    _admin_id: int = Depends(get_current_admin_id),
):
    if db.query(User.id).filter(User.username.ilike(user_data.username)).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=generate_password_hash(user_data.password) if user_data.password else None,
        is_admin=user_data.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if notify:
        background_tasks.add_task(_send_welcome_email, user)

    return user


@router.get("/", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _admin_id: int = Depends(get_current_admin_id),
):
    return db.query(User).order_by(User.id).all()


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin_id: int = Depends(get_current_admin_id),
):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    _admin_id: int = Depends(get_current_admin_id),
):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user_data.username is not None:
        duplicate = db.query(User.id).filter(
            User.username.ilike(user_data.username), User.id != user_id
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Username already exists")
        user.username = user_data.username
    if user_data.email is not None:
        user.email = user_data.email
    if user_data.password is not None:
        user.password_hash = generate_password_hash(user_data.password)
    if user_data.is_admin is not None:
        if user.is_admin and not user_data.is_admin:
            admin_count = db.query(User).filter(User.is_admin.is_(True)).count()
            if admin_count == 1:
                raise HTTPException(status_code=409, detail="Cannot demote the last administrator")
        user.is_admin = user_data.is_admin
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin_id: int = Depends(get_current_admin_id),
):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_admin and db.query(User).filter(User.is_admin.is_(True)).count() == 1:
        raise HTTPException(status_code=409, detail="Cannot delete the last administrator")
    if user_id == admin_id:
        raise HTTPException(status_code=409, detail="Cannot delete your own account")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}
