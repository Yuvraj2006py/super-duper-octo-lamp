from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas import LoginRequest, LoginResponse
from app.core.security import create_session_token, validate_login_api_key
from app.db import crud

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    validate_login_api_key(payload.api_key)
    user = crud.get_single_user(db)
    if not user:
        raise HTTPException(status_code=404, detail="No user seeded. Run make seed first.")
    token = create_session_token(str(user.id))
    return LoginResponse(token=token, user_id=str(user.id))
