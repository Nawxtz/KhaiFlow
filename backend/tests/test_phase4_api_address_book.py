from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session


def test_api_address_book_crud_and_jsonb_storage(client: TestClient, db_session: Session):
    """
    Verify CRUD on /api/address-book:
    1. Schema inspection: shop_id indexed, address_json is JSONB.
    2. POST /api/address-book persists structured JSON.
    3. GET /api/address-book lists and filters by user ID.
    4. GET /api/address-book/{id} retrieves entry.
    5. DELETE /api/address-book/{id} removes entry.
    """
    # 1. Schema check: verify column types and index
    inspector = inspect(db_session.bind)
    columns = {c["name"]: c for c in inspector.get_columns("address_book")}
    assert "shop_id" in columns
    assert "address_json" in columns

    indexes = inspector.get_indexes("address_book")
    indexed_columns = [idx["column_names"][0] for idx in indexes if idx.get("column_names")]
    assert "shop_id" in indexed_columns
    assert "line_user_id" in indexed_columns

    user_id = "U_crud_test_01"
    address_payload = {
        "shop_id": "shop_main",
        "line_user_id": user_id,
        "label": "Home",
        "receiver_name": "Somchai Sailom",
        "phone": "0812345678",
        "address_json": {
            "receiver_name": "Somchai Sailom",
            "phone": "0812345678",
            "house_number": "123/45",
            "street": "Sukhumvit Road",
            "subdistrict": "Khlong Toei",
            "district": "Khlong Toei",
            "province": "Bangkok",
            "postcode": "10110",
            "full_address": "123/45 Sukhumvit Road Khlong Toei Khlong Toei Bangkok 10110",
        },
        "is_default": True,
    }

    # 2. POST create
    res_post = client.post("/api/address-book", json=address_payload)
    assert res_post.status_code == 201
    created = res_post.json()
    addr_id = created["id"]
    assert created["line_user_id"] == user_id
    assert created["is_default"] is True
    assert created["address_json"]["postcode"] == "10110"

    # 3. GET list
    res_list = client.get(f"/api/address-book?line_user_id={user_id}")
    assert res_list.status_code == 200
    entries = res_list.json()
    assert len(entries) == 1
    assert entries[0]["id"] == addr_id

    # 4. GET by ID
    res_get = client.get(f"/api/address-book/{addr_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == addr_id

    # 5. DELETE
    res_del = client.delete(f"/api/address-book/{addr_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # Verify 404 after delete
    res_get_after = client.get(f"/api/address-book/{addr_id}")
    assert res_get_after.status_code == 404
