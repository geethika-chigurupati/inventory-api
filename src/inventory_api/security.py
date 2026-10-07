"""Password hashing (scrypt, standard library) and JWT helpers (HS256)."""
import hashlib
import hmac
import os
import time
from typing import Any

import jwt

ALGORITHM = "HS256"
ISSUER = "inventory-api"
ROLE_LEVEL = {"viewer": 1, "staff": 2, "admin": 3}

_N, _R, _P = 2**14, 8, 1


class TokenError(Exception):
    """Token is missing, invalid, or expired."""


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p)
        )
        return hmac.compare_digest(candidate, bytes.fromhex(digest_hex))
    except ValueError:
        return False


# Verified against when the username doesn't exist, so login takes similar time either way.
DUMMY_HASH = hash_password("not-a-real-password")


def create_access_token(secret: str, username: str, ttl_seconds: int) -> str:
    now = int(time.time())
    claims = {"iss": ISSUER, "sub": username, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],  # the token header cannot pick the algorithm
            issuer=ISSUER,
            options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc
