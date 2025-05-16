#use this file to check auth tokens when user uploads work.
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import HTTPException, Header
from typing import Optional
import os

# Secret key for signing the JWT — keep this secure!
SECRET_KEY = os.getenv("SECRET_KEY")  # ideally from os.environ
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # Token expires after 1 hour

def create_token_for_user(user_id: int) -> str:
    expire = datetime.now().astimezone() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id), "exp": expire}
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

def verify_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return int(user_id)
    except JWTError:
        return None
    
def get_current_user_id(authorization: str = Header(...)) -> int:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    token = authorization[7:]  # Strip 'Bearer '
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id