from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import verify_session_token
from app.db import crud
from app.db.models import User
from app.db.session import get_db_session


def get_db() -> Session:
    yield from get_db_session()


def require_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    user_id = verify_session_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token")

    user = crud.get_single_user(db)
    if not user or str(user.id) != str(user_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
