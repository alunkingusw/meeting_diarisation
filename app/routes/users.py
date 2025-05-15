# app/routers/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models import User
from app.db_dependency import get_db

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/")
def create_user(username: str, db: Session = Depends(get_db)):
    user = User(username=username)
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
def update_user(user_id: int, username: str, db: Session = Depends(get_db)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.username = username
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
