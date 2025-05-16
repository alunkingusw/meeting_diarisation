# backend/routers/users.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from backend.models import User
from backend.db_dependency import get_db
from backend.auth import create_token_for_user
from backend.validation import LoginRequest
from backend.validation import UserCreateEdit

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/login")
async def generate_token(
    payload: LoginRequest,
    db: Session = Depends(get_db)
):
    user_id = payload.user_id

    # validate user exists in DB:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_token_for_user(user_id)
    return {"token": token}

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
