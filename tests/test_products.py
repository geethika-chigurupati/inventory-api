def test_create_and_get(client, auth_header, seeded_product):
    assert seeded_product["sku"] == "SKU-1"
    assert seeded_product["price"] == "9.99"
    response = client.get(f"/products/{seeded_product['id']}", headers=auth_header("viewer"))
    assert response.json()["name"] == "Widget"


def test_duplicate_sku_conflicts(client, auth_header, seeded_product):
    response = client.post(
        "/products",
        json={"sku": "SKU-1", "name": "Other", "price": "1.00"},
        headers=auth_header("admin"),
    )
    assert response.status_code == 409


def test_unknown_product_is_404(client, auth_header):
    assert client.get("/products/9999", headers=auth_header("viewer")).status_code == 404


def test_product_validation(client, auth_header):
    headers = auth_header("admin")
    for body in (
        {"sku": "A", "name": "N", "price": "-1"},
        {"sku": "A", "name": "N", "price": "1.234"},
        {"sku": "A", "name": "N", "price": "1.00", "stock": -1},
        {"sku": "", "name": "N", "price": "1.00"},
    ):
        assert client.post("/products", json=body, headers=headers).status_code == 422


def test_stock_cannot_go_below_zero(client, auth_header, seeded_product):
    headers = auth_header("staff")
    url = f"/products/{seeded_product['id']}/stock"
    assert client.patch(url, json={"delta": -5}, headers=headers).json()["stock"] == 0
    response = client.patch(url, json={"delta": -1}, headers=headers)
    assert response.status_code == 409
    assert client.get(f"/products/{seeded_product['id']}", headers=headers).json()["stock"] == 0


def test_stock_change_on_unknown_product_is_404(client, auth_header):
    response = client.patch("/products/9999/stock", json={"delta": 1}, headers=auth_header("staff"))
    assert response.status_code == 404


def test_zero_delta_rejected(client, auth_header, seeded_product):
    url = f"/products/{seeded_product['id']}/stock"
    assert client.patch(url, json={"delta": 0}, headers=auth_header("staff")).status_code == 422


def test_pagination(client, auth_header):
    admin = auth_header("admin")
    for i in range(5):
        body = {"sku": f"P-{i}", "name": f"Item {i}", "price": "1.00"}
        assert client.post("/products", json=body, headers=admin).status_code == 201
    viewer = auth_header("viewer")
    first = client.get("/products?limit=2&offset=0", headers=viewer).json()
    second = client.get("/products?limit=2&offset=2", headers=viewer).json()
    assert [p["sku"] for p in first] == ["P-0", "P-1"]
    assert [p["sku"] for p in second] == ["P-2", "P-3"]
    assert client.get("/products?limit=0", headers=viewer).status_code == 422
    assert client.get("/products?limit=101", headers=viewer).status_code == 422
