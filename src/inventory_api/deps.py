from collections.abc import Callable, Iterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .cache import Cache
from .config import get_settings
from .models import User
from .security import ROLE_LEVEL, TokenError, decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_cache(request: Request) -> Cache:
    return request.app.state.cache


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "invalid or missing credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials, get_settings().jwt_secret)
    except TokenError as exc:
        raise unauthorized from exc
    # The role comes from the database, not the token, so role changes and deleted users
    # take effect immediately.
    user = db.scalar(select(User).where(User.username == claims["sub"]))
    if user is None:
        raise unauthorized
    return user


def require_role(minimum: str) -> Callable[[User], User]:
    def checker(user: User = Depends(current_user)) -> User:
        if ROLE_LEVEL[user.role] < ROLE_LEVEL[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires the {minimum} role")
        return user

    return checker
