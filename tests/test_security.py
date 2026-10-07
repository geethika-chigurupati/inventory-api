import time

import jwt
import pytest

from inventory_api.security import (
    ALGORITHM,
    ROLE_LEVEL,
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SECRET = "s" * 40


def test_password_round_trip():
    stored = hash_password("a-long-password")
    assert verify_password("a-long-password", stored)
    assert not verify_password("wrong", stored)


def test_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


def test_malformed_stored_hash_fails_closed():
    assert not verify_password("x", "garbage")
    assert not verify_password("x", "md5$1$2$3$aa$bb")


def test_token_round_trip():
    claims = decode_access_token(create_access_token(SECRET, "alice", 60), SECRET)
    assert claims["sub"] == "alice"


def test_wrong_secret_rejected():
    token = create_access_token(SECRET, "alice", 60)
    with pytest.raises(TokenError, match="invalid"):
        decode_access_token(token, "z" * 40)


def test_expired_token_rejected():
    token = create_access_token(SECRET, "alice", -5)
    with pytest.raises(TokenError, match="expired"):
        decode_access_token(token, SECRET)


def test_unsigned_token_rejected():
    claims = {"iss": "inventory-api", "sub": "alice", "exp": int(time.time()) + 60}
    with pytest.raises(TokenError):
        decode_access_token(jwt.encode(claims, key=None, algorithm="none"), SECRET)


def test_token_without_expiry_rejected():
    token = jwt.encode({"iss": "inventory-api", "sub": "alice"}, SECRET, algorithm=ALGORITHM)
    with pytest.raises(TokenError):
        decode_access_token(token, SECRET)


def test_role_ordering():
    assert ROLE_LEVEL["viewer"] < ROLE_LEVEL["staff"] < ROLE_LEVEL["admin"]
