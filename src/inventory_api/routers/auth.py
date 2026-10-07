from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import get_db
from ..models import User
from ..schemas import LoginRequest, TokenResponse
from ..security import DUMMY_HASH, create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    settings = get_settings()
    user = db.scalar(select(User).where(User.username == body.username))
    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect username or password")
    token = create_access_token(settings.jwt_secret, user.username, settings.token_ttl_seconds)
    return TokenResponse(access_token=token, expires_in=settings.token_ttl_seconds)
