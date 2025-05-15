# app/routers/groups.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models import Group
from app.db_dependency import get_db

router = APIRouter(prefix="/groups", tags=["groups"])

@router.post("/")
def create_group(name: str, db: Session = Depends(get_db)):
    group = Group(name=name)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group

@router.get("/")
def list_groups(db: Session = Depends(get_db)):
    return db.query(Group).all()

@router.get("/{group_id}")
def get_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(Group).get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group

@router.put("/{group_id}")
def update_group(group_id: int, name: str, db: Session = Depends(get_db)):
    group = db.query(Group).get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    group.name = name
    db.commit()
    return group

@router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(Group).get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    db.delete(group)
    db.commit()
    return {"message": "Group deleted"}