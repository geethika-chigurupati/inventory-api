import redis
from sqlalchemy import text

from inventory_api.cache import Cache


def test_get_is_served_from_cache(client, engine, redis_client, auth_header, seeded_product):
    headers = auth_header("viewer")
    url = f"/products/{seeded_product['id']}"
    assert client.get(url, headers=headers).json()["name"] == "Widget"
    assert redis_client.exists(f"product:{seeded_product['id']}")

    # Change the row behind the API's back: the cached copy should still be returned.
    with engine.begin() as conn:
        conn.execute(text("UPDATE products SET name = 'Changed' WHERE id = :i"), {"i": 1})
    assert client.get(url, headers=headers).json()["name"] == "Widget"


def test_stock_change_invalidates_cached_product(client, auth_header, seeded_product):
    url = f"/products/{seeded_product['id']}"
    viewer = auth_header("viewer")
    assert client.get(url, headers=viewer).json()["stock"] == 5  # now cached
    client.patch(f"{url}/stock", json={"delta": 2}, headers=auth_header("staff"))
    assert client.get(url, headers=viewer).json()["stock"] == 7


def test_create_invalidates_cached_list(client, auth_header, seeded_product):
    viewer = auth_header("viewer")
    assert len(client.get("/products", headers=viewer).json()) == 1  # now cached
    body = {"sku": "SKU-9", "name": "New", "price": "2.00"}
    client.post("/products", json=body, headers=auth_header("admin"))
    assert len(client.get("/products", headers=viewer).json()) == 2


def test_delete_invalidates_cache(client, auth_header, seeded_product):
    url = f"/products/{seeded_product['id']}"
    viewer = auth_header("viewer")
    assert client.get(url, headers=viewer).status_code == 200
    client.delete(url, headers=auth_header("admin"))
    assert client.get(url, headers=viewer).status_code == 404
    assert client.get("/products", headers=viewer).json() == []


class BrokenRedis:
    """Every call fails, like an unreachable Redis server."""

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise redis.ConnectionError("redis is down")

        return fail


def test_cache_fails_open_when_redis_is_down(engine, make_user):
    from fastapi.testclient import TestClient

    from inventory_api.main import create_app
    from tests.conftest import PASSWORD

    make_user("root", "admin")
    app = create_app(engine=engine, cache=Cache(BrokenRedis()))
    with TestClient(app) as client:
        token = client.post("/auth/login", json={"username": "root", "password": PASSWORD})
        headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
        created = client.post(
            "/products", json={"sku": "S", "name": "N", "price": "1.00"}, headers=headers
        )
        assert created.status_code == 201
        assert client.get("/products", headers=headers).status_code == 200
        assert client.get(f"/products/{created.json()['id']}", headers=headers).status_code == 200
