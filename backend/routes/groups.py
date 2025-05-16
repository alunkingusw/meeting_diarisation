# backend/routers/groups.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import Group, User
from backend.db_dependency import get_db
from backend.auth import get_current_user_id
from backend.validation import GroupCreateEdit

router = APIRouter(prefix="/groups", tags=["groups"])

@router.post("/")
def create_group(group_data: GroupCreateEdit, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_group = Group(name=group_data.name)
    new_group.users.append(user)  # Associate this group with the user
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group

@router.get("/")
def list_groups(db: Session = Depends(get_db), user_id:int = Depends(get_current_user_id)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.groups  # Only the groups associated with this user

@router.get("/{group_id}")
def get_group(group_id: int, db: Session = Depends(get_db), user_id:int = Depends(get_current_user_id)):
    group = db.query(Group).get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    #check ownership of the group, make sure this user is allowed to view it
    if user_id not in [member.id for member in group.users]:
        raise HTTPException(status_code=403, detail="Not authorised to view this group")
    
    return group

@router.put("/{group_id}")
def update_group(group_id: int, name: str, group_data: GroupCreateEdit, db: Session = Depends(get_db), user_id:int = Depends(get_current_user_id)):
    group = db.query(Group).get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    #check ownership of the group, make sure this user is allowed to view it
    if user_id not in [member.id for member in group.users]:
        raise HTTPException(status_code=403, detail="Not authorised to edit this group")
    
    group.name = name
    db.commit()
    return group

@router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), user_id:int = Depends(get_current_user_id)):
    group = db.query(Group).get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if user_id not in [member.id for member in group.users]:
        raise HTTPException(status_code=403, detail="Not authorised to delete this group")
    
    db.delete(group)
    db.commit()
    return {"message": "Group deleted"}