"""App factory. Run with: uvicorn inventory_api.main:create_app --factory"""
import logging
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import sessionmaker

from .cache import Cache
from .config import get_settings
from .models import Base, User
from .routers import auth, products, users
from .security import hash_password

log = logging.getLogger("inventory")


def _bootstrap_admin(session_factory: sessionmaker) -> None:
    """Create the first admin from ADMIN_USERNAME/ADMIN_PASSWORD if there are no users yet."""
    settings = get_settings()
    if not (settings.admin_username and settings.admin_password):
        return
    with session_factory() as session:
        if session.scalar(select(User.id).limit(1)) is not None:
            return
        session.add(
            User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role="admin",
            )
        )
        session.commit()
        log.info("created initial admin user %s", settings.admin_username)


def create_app(engine: Engine | None = None, cache: Cache | None = None) -> FastAPI:
    settings = get_settings()
    engine = engine or create_engine(settings.database_url, pool_pre_ping=True)
    cache = cache or Cache(
        redis.Redis.from_url(settings.redis_url), ttl_seconds=settings.cache_ttl_seconds
    )
    session_factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        _bootstrap_admin(session_factory)
        yield

    app = FastAPI(title="Inventory API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.cache = cache

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(products.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
