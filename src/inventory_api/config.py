import os
from dataclasses import dataclass
from functools import lru_cache

MIN_SECRET_LENGTH = 32


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    jwt_secret: str
    token_ttl_seconds: int
    cache_ttl_seconds: int
    admin_username: str | None
    admin_password: str | None


@lru_cache
def get_settings() -> Settings:
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(f"JWT_SECRET must be set and at least {MIN_SECRET_LENGTH} characters")
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL", "postgresql+psycopg://inventory:inventory@localhost:5432/inventory"
        ),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        jwt_secret=secret,
        token_ttl_seconds=int(os.getenv("TOKEN_TTL_SECONDS", "1800")),
        cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "60")),
        admin_username=os.getenv("ADMIN_USERNAME"),
        admin_password=os.getenv("ADMIN_PASSWORD"),
    )
