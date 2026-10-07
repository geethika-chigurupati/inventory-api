import os

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from inventory_api.cache import Cache
from inventory_api.config import get_settings
from inventory_api.main import create_app
from inventory_api.models import Base, User
from inventory_api.security import hash_password

SECRET = "t" * 40
PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture
def cache(redis_client):
    return Cache(redis_client, ttl_seconds=60)


@pytest.fixture
def client(engine, cache):
    with TestClient(create_app(engine=engine, cache=cache)) as test_client:
        yield test_client


@pytest.fixture
def make_user(engine):
    def _make(username: str, role: str) -> None:
        with sessionmaker(engine)() as session:
            session.add(User(username=username, password_hash=hash_password(PASSWORD), role=role))
            session.commit()

    return _make


@pytest.fixture
def auth_header(client, make_user):
    created: set[str] = set()

    def _header(role: str) -> dict[str, str]:
        username = f"{role}-user"
        if username not in created:  # safe to call several times in one test
            make_user(username, role)
            created.add(username)
        response = client.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _header


@pytest.fixture
def seeded_product(client, auth_header):
    headers = auth_header("admin")
    response = client.post(
        "/products", json={"sku": "SKU-1", "name": "Widget", "price": "9.99", "stock": 5},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def pytest_collection_modifyitems(config, items):
    if os.getenv("TEST_DATABASE_URL") and os.getenv("TEST_REDIS_URL"):
        return
    skip = pytest.mark.skip(reason="set TEST_DATABASE_URL and TEST_REDIS_URL to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
