"""Runs against real PostgreSQL and Redis. Skipped unless both URLs are set:

    TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/db
    TEST_REDIS_URL=redis://localhost:6379/1
"""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inventory_api.cache import Cache
from inventory_api.main import create_app
from inventory_api.models import Base, User
from inventory_api.security import hash_password
from tests.conftest import PASSWORD

pytestmark = pytest.mark.integration


@pytest.fixture
def real_engine():
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_size=20, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def real_redis():
    client = redis.Redis.from_url(os.environ["TEST_REDIS_URL"])
    client.flushdb()
    yield client
    client.flushdb()
    client.close()


@pytest.fixture
def live(real_engine, real_redis):
    with sessionmaker(real_engine)() as session:
        for name, role in (("root", "admin"), ("clerk", "staff"), ("guest", "viewer")):
            session.add(User(username=name, password_hash=hash_password(PASSWORD), role=role))
        session.commit()
    with TestClient(create_app(engine=real_engine, cache=Cache(real_redis))) as client:

        def header(name: str) -> dict[str, str]:
            response = client.post("/auth/login", json={"username": name, "password": PASSWORD})
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        yield client, header, real_redis


def test_full_flow_with_real_services(live):
    client, header, real_redis = live
    created = client.post(
        "/products",
        json={"sku": "REAL-1", "name": "Real widget", "price": "12.50", "stock": 3},
        headers=header("root"),
    )
    assert created.status_code == 201
    product_id = created.json()["id"]

    assert client.get(f"/products/{product_id}", headers=header("guest")).status_code == 200
    assert real_redis.exists(f"product:{product_id}") == 1  # cached in real Redis

    client.patch(f"/products/{product_id}/stock", json={"delta": 4}, headers=header("clerk"))
    assert real_redis.exists(f"product:{product_id}") == 0  # invalidated by the write
    assert client.get(f"/products/{product_id}", headers=header("guest")).json()["stock"] == 7


def test_database_enforces_unique_sku_and_nonnegative_stock(live, real_engine):
    client, header, _ = live
    body = {"sku": "DUP", "name": "A", "price": "1.00"}
    assert client.post("/products", json=body, headers=header("root")).status_code == 201
    assert client.post("/products", json=body, headers=header("root")).status_code == 409


def test_concurrent_stock_removal_never_oversells(live):
    client, header, _ = live
    created = client.post(
        "/products",
        json={"sku": "RACE", "name": "Scarce", "price": "1.00", "stock": 10},
        headers=header("root"),
    )
    product_id = created.json()["id"]
    clerk = header("clerk")

    def remove_one(_: int) -> int:
        response = client.patch(
            f"/products/{product_id}/stock", json={"delta": -1}, headers=clerk
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(remove_one, range(30)))

    assert statuses.count(200) == 10
    assert statuses.count(409) == 20
    assert client.get(f"/products/{product_id}", headers=header("guest")).json()["stock"] == 0
