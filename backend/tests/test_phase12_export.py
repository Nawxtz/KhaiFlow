"""Tests for Phase 12: Carrier CSV export.

Covers:
- Carrier mapper interface & normalization
- Built-in Kerry Express Thailand and Thailand Post EMS configs
- Reviewer Item 1: Two carrier configs produce two different CSV shapes from same data
- Reviewer Item 2: Missing required field in config raises CarrierConfigError before output
- Reviewer Item 3: Export endpoint returns correct Content-Type and Content-Disposition headers
- Order fulfillment status rejection guard (unfulfilled orders rejected)
- Pluggable config loading without core modifications
- RBAC permissions (staff rejected 403, owner allowed 200)
- Audit logging on export
- Empty export returns 200 with headers only
- Transformers (date_th, phone_format, identity)
"""

import csv
import io
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.address_book import AddressBook
from app.models.order import Order, OrderItem, OrderStatus
from app.services.carrier_mapper import (
    CarrierConfig,
    CarrierConfigError,
    FieldMapping,
    OrderExportRow,
    map_orders_to_csv,
    transform_date_th,
    transform_identity,
    transform_phone_format,
)
from app.services.export_service import (
    InvalidOrderStateForExportError,
    export_fulfilled_orders,
    load_carrier_config,
)


def _create_sample_fulfilled_order(
    db: Session,
    order_id: str = "ORD-TEST-1201",
    shop_id: str = "default",
    line_user_id: str = "U_carrier_buyer_01",
    status: str = OrderStatus.FULFILLED.value,
) -> Order:
    """Helper to create a populated fulfilled order with address and line items."""
    # Create AddressBook entry
    address = AddressBook(
        shop_id=shop_id,
        line_user_id=line_user_id,
        label="Home",
        receiver_name="Somchai Jaidee",
        phone="+66 81 234 5678",
        address_json={
            "receiver_name": "Somchai Jaidee",
            "phone": "+66 81 234 5678",
            "house_number": "123/45",
            "street": "Sukhumvit Road",
            "subdistrict": "Khlong Toei",
            "district": "Khlong Toei",
            "province": "Bangkok",
            "postcode": "10110",
            "full_address": "123/45 Sukhumvit Road, Khlong Toei, Khlong Toei, Bangkok 10110",
        },
        is_default=True,
    )
    db.add(address)

    # Create Order
    order = Order(
        id=order_id,
        shop_id=shop_id,
        line_user_id=line_user_id,
        status=status,
        total=Decimal("990.00"),
        currency="THB",
        created_at=datetime(2026, 9, 23, 10, 30, 0, tzinfo=UTC),
    )
    db.add(order)

    # Create Line Items
    item1 = OrderItem(
        order_id=order_id,
        shop_id=shop_id,
        sku="SKU-SILK-001",
        name="Thai Silk Scarf",
        size="M",
        qty=2,
        unit_price=Decimal("450.00"),
        line_total=Decimal("900.00"),
    )
    item2 = OrderItem(
        order_id=order_id,
        shop_id=shop_id,
        sku="SKU-MUG-002",
        name="Clay Mug",
        size=None,
        qty=1,
        unit_price=Decimal("90.00"),
        line_total=Decimal("90.00"),
    )
    db.add(item1)
    db.add(item2)
    order.items = [item1, item2]

    db.commit()
    db.refresh(order)
    return order


# ==============================================================================
# REVIEWER ITEM 1: Two carrier configs produce two different CSV shapes from same data
# ==============================================================================


def test_reviewer_item_1_two_carrier_configs_produce_different_csv_shapes():
    """
    Reviewer Verification Item 1:
    Two carrier configs (Kerry and Thailand Post) produce two different CSV column
    shapes (headers, column count, and field sequence) from the exact same order data.
    """
    kerry_cfg = load_carrier_config("kerry")
    th_post_cfg = load_carrier_config("thailand_post")

    sample_orders = [
        OrderExportRow(
            order_id="ORD-001",
            receiver_name="Somchai Jaidee",
            phone="+66 81 234 5678",
            full_address="123 Sukhumvit, Bangkok 10110",
            subdistrict="Khlong Toei",
            district="Khlong Toei",
            province="Bangkok",
            postcode="10110",
            total=Decimal("990.00"),
            sku="SKU-001",
            qty=2,
            tracking_note="Leave at front door",
            order_date=datetime(2026, 9, 23, 10, 0, 0, tzinfo=UTC),
        )
    ]

    kerry_csv = map_orders_to_csv(sample_orders, kerry_cfg)
    th_post_csv = map_orders_to_csv(sample_orders, th_post_cfg)

    # Clean BOM for parsing comparison
    kerry_reader = list(csv.reader(io.StringIO(kerry_csv.lstrip("\ufeff"))))
    th_post_reader = list(csv.reader(io.StringIO(th_post_csv.lstrip("\ufeff"))))

    kerry_headers = kerry_reader[0]
    th_post_headers = th_post_reader[0]

    # Kerry has 12 columns; Thailand Post has 9 columns
    assert len(kerry_headers) == 12
    assert len(th_post_headers) == 9
    assert kerry_headers != th_post_headers

    # Specific headers match carrier expectations
    assert kerry_headers[0] == "Recipient Name"
    assert kerry_headers[1] == "Mobile Phone"
    assert kerry_headers[7] == "Order No"
    assert kerry_headers[8] == "COD Amount"

    assert th_post_headers[0] == "EMS Reference"
    assert th_post_headers[1] == "Consignee Name"
    assert th_post_headers[2] == "Contact Number"
    assert th_post_headers[7] == "Collection Amount"

    # Data row checks: both received same order data but mapped differently
    kerry_row = kerry_reader[1]
    th_post_row = th_post_reader[1]

    # Phone is normalized to 0812345678 in both, but at different column indices
    assert kerry_row[1] == "0812345678"  # Mobile Phone at col 1
    assert th_post_row[2] == "0812345678"  # Contact Number at col 2

    # Order ID is at index 7 in Kerry, index 0 in Thailand Post
    assert kerry_row[7] == "ORD-001"
    assert th_post_row[0] == "ORD-001"


# ==============================================================================
# REVIEWER ITEM 2: Missing required field in config raises CarrierConfigError
# ==============================================================================


def test_reviewer_item_2_missing_required_field_raises_carrier_config_error():
    """
    Reviewer Verification Item 2:
    A carrier config with a missing required field raises CarrierConfigError
    before generating any CSV output.
    """
    bad_config = CarrierConfig(
        carrier_id="invalid_carrier",
        carrier_name="Invalid Carrier Express",
        fields=[
            FieldMapping(source="order_id", header="Order ID"),
            FieldMapping(source="non_existent_source_field_xyz", header="Non-existent"),
        ],
        encoding="utf-8",
    )

    sample_orders = [
        OrderExportRow(
            order_id="ORD-001",
            receiver_name="Somchai",
            phone="0812345678",
            full_address="Bangkok",
        )
    ]

    with pytest.raises(CarrierConfigError) as exc_info:
        map_orders_to_csv(sample_orders, bad_config)

    assert "non_existent_source_field_xyz" in str(exc_info.value)
    assert "missing" in str(exc_info.value).lower() or "schema" in str(exc_info.value).lower()


def test_unknown_transform_raises_carrier_config_error():
    """Unknown transformer name in config raises CarrierConfigError."""
    bad_config = CarrierConfig(
        carrier_id="invalid_transform_carrier",
        carrier_name="Invalid Transform Carrier",
        fields=[
            FieldMapping(source="order_id", header="Order ID", transform="unsupported_transform_type"),
        ],
    )

    sample_orders = [
        OrderExportRow(
            order_id="ORD-001",
            receiver_name="Somchai",
            phone="0812345678",
            full_address="Bangkok",
        )
    ]

    with pytest.raises(CarrierConfigError) as exc_info:
        map_orders_to_csv(sample_orders, bad_config)

    assert "unsupported_transform_type" in str(exc_info.value)


# ==============================================================================
# REVIEWER ITEM 3: Export endpoint headers and download verification
# ==============================================================================


def test_reviewer_item_3_export_endpoint_returns_correct_headers(client: TestClient, db_session: Session):
    """
    Reviewer Verification Item 3:
    The export endpoint returns the CSV with correct Content-Type: text/csv and
    Content-Disposition: attachment headers.
    """
    _create_sample_fulfilled_order(db=db_session, order_id="ORD-HDR-01", shop_id="default")

    res = client.get("/api/export/csv?carrier_id=kerry&shop_id=default", headers={"X-User-Role": "owner"})
    assert res.status_code == 200

    # Verify Content-Type contains text/csv
    content_type = res.headers.get("content-type", "")
    assert "text/csv" in content_type

    # Verify Content-Disposition contains attachment and filename
    content_disp = res.headers.get("content-disposition", "")
    assert "attachment" in content_disp
    assert 'filename="kerry_' in content_disp
    assert content_disp.endswith('.csv"')

    # Verify content body is valid CSV
    text_content = res.text
    assert "Recipient Name" in text_content
    assert "ORD-HDR-01" in text_content
    assert "Somchai Jaidee" in text_content


# ==============================================================================
# ACCEPTANCE CRITERIA: Unfulfilled Order Rejection
# ==============================================================================


@pytest.mark.parametrize(
    "unfulfilled_status",
    [
        OrderStatus.BROWSING.value,
        OrderStatus.ORDER_DRAFT.value,
        OrderStatus.ORDER_CONFIRMED.value,
        OrderStatus.ADDRESS_COLLECTION.value,
        OrderStatus.ADDRESS_CONFIRMED.value,
        OrderStatus.STOCK_RESERVED.value,
        OrderStatus.AWAITING_PAYMENT.value,
        OrderStatus.PAYMENT_RECEIVED.value,
    ],
)
def test_unfulfilled_order_rejected_from_export(db_session: Session, unfulfilled_status: str):
    """
    Acceptance Criteria from §20 & TEST_PLAN.md:
    An order not in FULFILLED status is rejected from export (cannot export unfulfilled orders).
    """
    unfulfilled_order = _create_sample_fulfilled_order(
        db=db_session,
        order_id=f"ORD-UNF-{unfulfilled_status}",
        status=unfulfilled_status,
    )

    with pytest.raises(InvalidOrderStateForExportError) as exc_info:
        export_fulfilled_orders(
            shop_id="default",
            carrier_id="kerry",
            db=db_session,
            orders=[unfulfilled_order],
        )

    assert unfulfilled_status in str(exc_info.value)
    assert "Only FULFILLED orders can be exported" in str(exc_info.value)


# ==============================================================================
# ACCEPTANCE CRITERIA: Pluggable Carrier Configs
# ==============================================================================


def test_pluggable_carrier_config_new_carrier_without_core_changes(tmp_path: Path):
    """
    Acceptance Criteria:
    Mapper is pluggable — new carriers can be added by dropping in a new config
    without changing core code.
    """
    custom_carrier_config = {
        "carrier_id": "flash_express",
        "carrier_name": "Flash Express Thailand",
        "fields": [
            {"source": "order_id", "header": "Waybill No", "transform": "identity"},
            {"source": "receiver_name", "header": "Customer", "transform": "identity"},
            {"source": "phone", "header": "Tel", "transform": "phone_format"},
            {"source": "province", "header": "Destination Province", "transform": "identity"},
            {"source": "total", "header": "COD", "transform": "identity"},
        ],
        "encoding": "utf-8-sig",
    }

    config_file = tmp_path / "flash_express.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(custom_carrier_config, f)

    loaded_cfg = load_carrier_config(carrier_id="flash_express", configs_dir=tmp_path)
    assert loaded_cfg.carrier_name == "Flash Express Thailand"
    assert len(loaded_cfg.fields) == 5

    sample_orders = [
        OrderExportRow(
            order_id="ORD-FLASH-01",
            receiver_name="Anong Chai",
            phone="0899999999",
            full_address="Chiang Mai",
            province="Chiang Mai",
            total=Decimal("500.00"),
        )
    ]

    csv_output = map_orders_to_csv(sample_orders, loaded_cfg)
    assert "Waybill No,Customer,Tel,Destination Province,COD" in csv_output
    assert "ORD-FLASH-01,Anong Chai,0899999999,Chiang Mai,500.00" in csv_output


# ==============================================================================
# ACCEPTANCE CRITERIA: Transformers
# ==============================================================================


def test_transformers():
    """Test transformer functions for identity, date_th, and phone_format."""
    # Identity
    assert transform_identity("hello") == "hello"
    assert transform_identity(Decimal("123.40")) == "123.40"
    assert transform_identity(None) == ""

    # date_th
    dt = datetime(2026, 9, 23, 14, 0, 0)
    assert transform_date_th(dt) == "23/09/2026"
    assert transform_date_th("2026-09-23") == "23/09/2026"
    assert transform_date_th("2026-09-23T14:30:00") == "23/09/2026"
    assert transform_date_th(None) == ""

    # phone_format
    assert transform_phone_format("+66 81 234 5678") == "0812345678"
    assert transform_phone_format("081-234-5678") == "0812345678"
    assert transform_phone_format("66812345678") == "0812345678"
    assert transform_phone_format("812345678") == "0812345678"
    assert transform_phone_format(None) == ""


# ==============================================================================
# ACCEPTANCE CRITERIA: RBAC & Audit Logging
# ==============================================================================


def test_rbac_staff_cannot_trigger_owner_only_export(client: TestClient):
    """TEST_PLAN.md: Staff cannot trigger an owner-only export."""
    res = client.get(
        "/api/export/csv?carrier_id=kerry&shop_id=default",
        headers={"X-User-Role": "staff"},
    )
    assert res.status_code == 403
    assert "Staff role cannot trigger carrier export" in res.json()["detail"]


def test_rbac_owner_can_trigger_export(client: TestClient, db_session: Session):
    """Owner role is allowed to export."""
    _create_sample_fulfilled_order(db=db_session, order_id="ORD-OWNER-01")
    res = client.get(
        "/api/export/csv?carrier_id=kerry&shop_id=default",
        headers={"X-User-Role": "owner"},
    )
    assert res.status_code == 200


def test_export_action_logged_in_audit_log(db_session: Session, caplog: pytest.LogCaptureFixture):
    """TEST_PLAN.md: Export action is logged in the audit log."""
    _create_sample_fulfilled_order(db=db_session, order_id="ORD-AUDIT-01")

    export_logger = logging.getLogger("app.services.export_service")
    export_logger.disabled = False
    export_logger.propagate = True
    caplog.set_level(logging.INFO, logger="app.services.export_service")

    export_fulfilled_orders(shop_id="default", carrier_id="kerry", db=db_session)

    assert "AUDIT_EXPORT_CSV" in caplog.text
    assert "shop_id=default" in caplog.text
    assert "carrier_id=kerry" in caplog.text


# ==============================================================================
# EDGE CASES: Empty Export & Unknown Carrier
# ==============================================================================


def test_empty_export_returns_200_with_headers_only(client: TestClient):
    """
    TEST_PLAN.md: Empty export (no orders matching criteria) is handled cleanly:
    returns 200 with headers only.
    """
    res = client.get(
        "/api/export/csv?carrier_id=thailand_post&shop_id=empty_shop",
        headers={"X-User-Role": "owner"},
    )
    assert res.status_code == 200
    rows = list(csv.reader(io.StringIO(res.text.lstrip("\ufeff"))))
    assert len(rows) == 1  # Header row only
    assert rows[0][0] == "EMS Reference"
    assert rows[0][1] == "Consignee Name"


def test_unknown_carrier_returns_400(client: TestClient):
    """Unknown carrier_id returns 400 with clear error message."""
    res = client.get(
        "/api/export/csv?carrier_id=non_existent_carrier_99",
        headers={"X-User-Role": "owner"},
    )
    assert res.status_code == 400
    assert "carrier" in res.json()["detail"].lower()


def test_path_aliases(client: TestClient, db_session: Session):
    """v1_buildable_spec.md §19 route alias: POST /api/export/{carrier} and GET /api/export/{carrier}."""
    _create_sample_fulfilled_order(db=db_session, order_id="ORD-ALIAS-01")

    res_get = client.get("/api/export/kerry", headers={"X-User-Role": "owner"})
    assert res_get.status_code == 200
    assert "Recipient Name" in res_get.text

    res_post = client.post("/api/export/kerry", headers={"X-User-Role": "owner"})
    assert res_post.status_code == 200
    assert "Recipient Name" in res_post.text
