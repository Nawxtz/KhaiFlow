from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.order import Order, OrderItem, OrderStatus


@pytest.fixture
def seed_products(db_session: Session) -> list[Inventory]:
    items = [
        Inventory(
            sku="SKU-API-01",
            name="Handmade Silk Pillow",
            category="Home",
            price=Decimal("450.00"),
            stock=10,
            reserved=0,
            active=True,
        ),
        Inventory(
            sku="SKU-API-02",
            name="Organic Herbal Tea",
            category="Beverages",
            price=Decimal("150.00"),
            stock=5,
            reserved=0,
            active=True,
        ),
        Inventory(
            sku="SKU-API-03",
            name="Ceramic Bowl",
            category="Kitchen",
            price=Decimal("300.00"),
            stock=1,
            reserved=0,
            active=True,
        ),
    ]
    db_session.add_all(items)
    db_session.commit()
    return items


def test_api_create_order_programmatic(
    client: TestClient, db_session: Session, seed_products: list[Inventory]
):
    """POST /api/orders creates an order with items programmatically."""
    payload = {
        "shop_id": "default",
        "line_user_id": "U_api_user_01",
        "items": [
            {"sku": "SKU-API-01", "name": "Handmade Silk Pillow", "qty": 2, "size": "Standard"},
            {"sku": "SKU-API-02", "name": "Organic Herbal Tea", "qty": 1},
        ],
    }

    res = client.post("/api/orders", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["line_user_id"] == "U_api_user_01"
    assert data["shop_id"] == "default"
    assert data["status"] == OrderStatus.ORDER_DRAFT.value
    # Total: (450 * 2) + (150 * 1) = 900 + 150 = 1050.00
    assert Decimal(str(data["total"])) == Decimal("1050.00")
    assert len(data["items"]) == 2

    # Verify DB record
    order_in_db = db_session.query(Order).filter(Order.id == data["id"]).first()
    assert order_in_db is not None
    assert len(order_in_db.items) == 2


def test_api_get_orders_list_and_filters(
    client: TestClient, db_session: Session, seed_products: list[Inventory]
):
    """GET /api/orders returns orders with filtering by line_user_id, status, and shop_id."""
    o1 = Order(
        id="ORD-TEST-001",
        shop_id="shop_a",
        line_user_id="U_user_A",
        status=OrderStatus.ORDER_CONFIRMED.value,
        total=Decimal("450.00"),
    )
    o2 = Order(
        id="ORD-TEST-002",
        shop_id="shop_a",
        line_user_id="U_user_B",
        status=OrderStatus.ORDER_DRAFT.value,
        total=Decimal("150.00"),
    )
    o3 = Order(
        id="ORD-TEST-003",
        shop_id="shop_b",
        line_user_id="U_user_A",
        status=OrderStatus.ORDER_CONFIRMED.value,
        total=Decimal("300.00"),
    )
    db_session.add_all([o1, o2, o3])
    db_session.commit()

    # Filter by line_user_id
    res_user = client.get("/api/orders?line_user_id=U_user_A")
    assert res_user.status_code == 200
    ids_user = [o["id"] for o in res_user.json()]
    assert set(ids_user) == {"ORD-TEST-001", "ORD-TEST-003"}

    # Filter by status
    res_status = client.get("/api/orders?status=ORDER_DRAFT")
    assert res_status.status_code == 200
    ids_status = [o["id"] for o in res_status.json()]
    assert ids_status == ["ORD-TEST-002"]

    # Filter by shop_id
    res_shop = client.get("/api/orders?shop_id=shop_b")
    assert res_shop.status_code == 200
    assert len(res_shop.json()) == 1
    assert res_shop.json()[0]["id"] == "ORD-TEST-003"


def test_api_get_order_by_id(
    client: TestClient, db_session: Session, seed_products: list[Inventory]
):
    """GET /api/orders/{order_id} returns single order with items."""
    order = Order(
        id="ORD-SINGLE-01",
        shop_id="default",
        line_user_id="U_single_user",
        status=OrderStatus.ORDER_CONFIRMED.value,
        total=Decimal("450.00"),
    )
    db_session.add(order)
    db_session.commit()

    item = OrderItem(
        order_id="ORD-SINGLE-01",
        sku="SKU-API-01",
        name="Handmade Silk Pillow",
        qty=1,
        unit_price=Decimal("450.00"),
        line_total=Decimal("450.00"),
    )
    db_session.add(item)
    db_session.commit()

    res = client.get("/api/orders/ORD-SINGLE-01")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "ORD-SINGLE-01"
    assert data["status"] == OrderStatus.ORDER_CONFIRMED.value
    assert len(data["items"]) == 1
    assert data["items"][0]["sku"] == "SKU-API-01"

    # Non-existent ID returns 404
    res_not_found = client.get("/api/orders/ORD-NONEXISTENT")
    assert res_not_found.status_code == 404


def test_api_create_order_out_of_stock_rejected(client: TestClient, seed_products: list[Inventory]):
    """POST /api/orders with requested quantity exceeding stock returns 400."""
    payload = {
        "line_user_id": "U_test_user",
        "items": [
            {"sku": "SKU-API-03", "qty": 10},  # stock is 1
        ],
    }
    res = client.post("/api/orders", json=payload)
    assert res.status_code == 400
    assert "out of stock" in res.json()["detail"].lower()


def test_api_create_order_invalid_sku_rejected(client: TestClient, seed_products: list[Inventory]):
    """POST /api/orders with nonexistent SKU returns 400."""
    payload = {
        "line_user_id": "U_test_user",
        "items": [
            {"sku": "SKU-DOES-NOT-EXIST", "qty": 1},
        ],
    }
    res = client.post("/api/orders", json=payload)
    assert res.status_code == 400
    assert "not found" in res.json()["detail"].lower()
