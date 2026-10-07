from inventory_api.security import create_access_token
from tests.conftest import PASSWORD, SECRET


def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_login_success(client, make_user):
    make_user("alice", "viewer")
    response = client.post("/auth/login", json={"username": "alice", "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password(client, make_user):
    make_user("alice", "viewer")
    response = client.post("/auth/login", json={"username": "alice", "password": "nope-nope-nope"})
    assert response.status_code == 401


def test_login_unknown_user_gets_same_error(client, make_user):
    make_user("alice", "viewer")
    wrong = client.post("/auth/login", json={"username": "alice", "password": "bad"})
    unknown = client.post("/auth/login", json={"username": "ghost", "password": "bad"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_protected_route_without_token(client):
    assert client.get("/products").status_code == 401


def test_protected_route_with_garbage_token(client):
    response = client.get("/products", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_token_for_deleted_user_is_rejected(client):
    token = create_access_token(SECRET, "ghost", 60)  # valid signature, but no such user
    response = client.get("/products", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
