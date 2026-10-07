import pytest

NEW_PRODUCT = {"sku": "SKU-2", "name": "Gadget", "price": "5.00", "stock": 1}


def test_viewer_can_read_but_not_write(client, auth_header, seeded_product):
    headers = auth_header("viewer")
    assert client.get("/products", headers=headers).status_code == 200
    assert client.get(f"/products/{seeded_product['id']}", headers=headers).status_code == 200
    assert client.post("/products", json=NEW_PRODUCT, headers=headers).status_code == 403
    patch = client.patch(
        f"/products/{seeded_product['id']}/stock", json={"delta": 1}, headers=headers
    )
    assert patch.status_code == 403
    assert client.delete(f"/products/{seeded_product['id']}", headers=headers).status_code == 403


def test_staff_can_change_stock_only(client, auth_header, seeded_product):
    headers = auth_header("staff")
    patch = client.patch(
        f"/products/{seeded_product['id']}/stock", json={"delta": 3}, headers=headers
    )
    assert patch.status_code == 200
    assert patch.json()["stock"] == 8
    assert client.post("/products", json=NEW_PRODUCT, headers=headers).status_code == 403
    assert client.delete(f"/products/{seeded_product['id']}", headers=headers).status_code == 403


def test_admin_can_do_everything(client, auth_header, seeded_product):
    headers = auth_header("admin")
    assert client.post("/products", json=NEW_PRODUCT, headers=headers).status_code == 201
    assert client.delete(f"/products/{seeded_product['id']}", headers=headers).status_code == 204


def test_only_admin_can_create_users(client, auth_header):
    body = {"username": "newbie", "password": "a-long-password", "role": "staff"}
    for role in ("viewer", "staff"):
        assert client.post("/users", json=body, headers=auth_header(role)).status_code == 403


def test_admin_creates_user_who_can_log_in(client, auth_header):
    body = {"username": "newbie", "password": "a-long-password", "role": "staff"}
    created = client.post("/users", json=body, headers=auth_header("admin"))
    assert created.status_code == 201
    assert created.json() == {"id": created.json()["id"], "username": "newbie", "role": "staff"}
    login = client.post("/auth/login", json={"username": "newbie", "password": "a-long-password"})
    assert login.status_code == 200


def test_duplicate_username_conflicts(client, auth_header):
    headers = auth_header("admin")
    body = {"username": "dupe-user", "password": "a-long-password", "role": "viewer"}
    assert client.post("/users", json=body, headers=headers).status_code == 201
    assert client.post("/users", json=body, headers=headers).status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"username": "ab", "password": "a-long-password"},
        {"username": "valid-name", "password": "short"},
        {"username": "valid-name", "password": "a-long-password", "role": "superuser"},
        {"username": "bad name!", "password": "a-long-password"},
    ],
)
def test_user_validation(client, auth_header, body):
    assert client.post("/users", json=body, headers=auth_header("admin")).status_code == 422
