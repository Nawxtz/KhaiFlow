"""Tests for Phase 9: Fulfillment Sheet write + buyer notify.

Verifies:
1. Sheets API failure on first attempt -> retries -> exactly one row written total (not two).
2. Buyer notification fires strictly after successful sheet write — not on each retry attempt.
3. Duplicate fulfillment attempt (same order_id already in FULFILLED state) is safely skipped.
4. Order not in PAYMENT_RECEIVED status is rejected before touching Sheets API.
5. Exhausted retries leaves order in PAYMENT_RECEIVED and logs error without crashing.
6. LINE notification failure is caught and logged without aborting FULFILLED order status.
7. Fulfillment sheet row matches reference_schema.md columns.
8. API endpoint POST /api/orders/{order_id}/fulfill handles success, duplicates, invalid state, 404.
9. Strict schema governance: no new tables (fulfillment_outbox/sheet_outbox) and no synced_to_sheet column.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.line_client import LineClient
from app.models.address_book import AddressBook
from app.models.inventory import Inventory
from app.models.order import Order, OrderItem, OrderStatus
from app.services.fulfillment_service import (
    InvalidOrderStateForFulfillmentError,
    OrderNotFoundError,
    fulfill_order,
    fulfill_order_with_retry,
)
from app.services.sheet_ingest import SheetsAPIError
from tests.conftest import MockSheetsClient


@pytest.fixture
def test_order_ready_for_fulfillment(db_session: Session) -> Order:
    """Create a sample order in PAYMENT_RECEIVED status with items and address."""
    # 1. Product in inventory
    product = Inventory(
        sku="SKU-PHASE9-01",
        shop_id="default",
        name="Thai Silk Scarf Premium",
        category="Accessories",
        price=Decimal("450.00"),
        stock=20,
        reserved=1,
        active=True,
        version=1,
    )
    db_session.add(product)

    # 2. Address in AddressBook
    address = AddressBook(
        shop_id="default",
        line_user_id="U_PHASE9_TESTER",
        receiver_name="Somchai Jaidee",
        phone="0812345678",
        address_json={
            "receiver_name": "Somchai Jaidee",
            "phone": "0812345678",
            "house_number": "123/4",
            "street": "Sukhumvit Rd",
            "subdistrict": "Khlong Toei",
            "district": "Khlong Toei",
            "province": "Bangkok",
            "postcode": "10110",
            "full_address": "123/4 Sukhumvit Rd Khlong Toei Khlong Toei Bangkok 10110",
        },
        is_default=True,
    )
    db_session.add(address)

    # 3. Order in PAYMENT_RECEIVED
    order = Order(
        id="ORD-PHASE9-001",
        shop_id="default",
        line_user_id="U_PHASE9_TESTER",
        status=OrderStatus.PAYMENT_RECEIVED.value,
        total=Decimal("450.00"),
        currency="THB",
        approval_state="AUTO_CONFIRMED",
    )
    db_session.add(order)

    item = OrderItem(
        order_id=order.id,
        shop_id="default",
        sku="SKU-PHASE9-01",
        name="Thai Silk Scarf Premium",
        size=None,
        qty=1,
        unit_price=Decimal("450.00"),
        line_total=Decimal("450.00"),
    )
    db_session.add(item)
    order.items.append(item)

    db_session.commit()
    db_session.refresh(order)
    return order


def test_sheets_failure_first_attempt_retries_exactly_one_row_written(
    db_session: Session,
    test_order_ready_for_fulfillment: Order,
):
    """
    Required Test 1 & Verification Item 2:
    Simulates SheetsAPIError on first call, retries, verifies the mock's sheet-write
    method was called exactly 2 times total (first failed + one success), and verifies
    the order is in FULFILLED state with exactly one row written and exactly one notification sent.
    """
    order = test_order_ready_for_fulfillment
    mock_sheets = MockSheetsClient()
    mock_sheets.fail_next_n_appends = 1  # Fails 1st call, succeeds 2nd

    mock_line = MagicMock(spec=LineClient)

    # Execute fulfillment with retry wrapper
    result = fulfill_order_with_retry(
        order_id=order.id,
        db=db_session,
        sheets_client=mock_sheets,
        line_client_instance=mock_line,
        max_attempts=3,
    )

    # 1. Verification of outcome
    assert result.success is True
    assert result.status == OrderStatus.FULFILLED.value
    assert result.already_fulfilled is False

    # 2. Database state transitioned atomically to FULFILLED
    db_session.refresh(order)
    assert order.status == OrderStatus.FULFILLED.value

    # 3. Verify exactly 2 calls made to Sheets client (1 failed + 1 success)
    assert mock_sheets.append_call_count == 2

    # 4. Verify exactly ONE row written total to the sheet (not two)
    assert len(mock_sheets.appended_rows) == 1

    # 5. Verify buyer notification was called exactly once
    assert mock_line.push_message.call_count == 1
    call_args = mock_line.push_message.call_args
    assert call_args.kwargs["to"] == "U_PHASE9_TESTER"
    messages = call_args.kwargs["messages"]
    assert len(messages) == 1
    assert "ORD-PHASE9-001" in messages[0]["text"]


def test_buyer_notification_fires_strictly_after_successful_sheet_write(
    db_session: Session,
    test_order_ready_for_fulfillment: Order,
):
    """
    Required Test 2 & Verification Item 3:
    Verifies buyer notification is NOT sent if sheet write fails on the first attempt,
    and only fires once the sheet write commit succeeds.
    """
    order = test_order_ready_for_fulfillment
    mock_sheets = MockSheetsClient()
    mock_line = MagicMock(spec=LineClient)

    # Directly call fulfill_order with a failing sheet write
    mock_sheets.fail_next_n_appends = 1
    with pytest.raises(SheetsAPIError):
        fulfill_order(
            order_id=order.id,
            db=db_session,
            sheets_client=mock_sheets,
            line_client_instance=mock_line,
        )

    # Sheet write failed: order must STILL be in PAYMENT_RECEIVED
    db_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_RECEIVED.value

    # Notification must NOT have fired during the failed attempt
    assert mock_line.push_message.call_count == 0
    assert len(mock_sheets.appended_rows) == 0

    # Now attempt succeeds
    result = fulfill_order(
        order_id=order.id,
        db=db_session,
        sheets_client=mock_sheets,
        line_client_instance=mock_line,
    )
    assert result.success is True

    # Order is now FULFILLED and notification fired exactly once
    db_session.refresh(order)
    assert order.status == OrderStatus.FULFILLED.value
    assert mock_line.push_message.call_count == 1


def test_duplicate_fulfillment_attempt_safely_skipped_idempotent(
    db_session: Session,
    test_order_ready_for_fulfillment: Order,
):
    """
    Required Test 3:
    A duplicate fulfillment attempt (same order_id already in FULFILLED state) is safely
    skipped: does not write to Google Sheet again, does not send notification again.
    """
    order = test_order_ready_for_fulfillment
    mock_sheets = MockSheetsClient()
    mock_line = MagicMock(spec=LineClient)

    # 1. First fulfillment succeeds
    res1 = fulfill_order(
        order_id=order.id,
        db=db_session,
        sheets_client=mock_sheets,
        line_client_instance=mock_line,
    )
    assert res1.success is True
    assert res1.already_fulfilled is False
    assert mock_sheets.append_call_count == 1
    assert len(mock_sheets.appended_rows) == 1
    assert mock_line.push_message.call_count == 1

    # 2. Second fulfillment attempt for the same order
    res2 = fulfill_order(
        order_id=order.id,
        db=db_session,
        sheets_client=mock_sheets,
        line_client_instance=mock_line,
    )
    assert res2.success is True
    assert res2.already_fulfilled is True
    assert res2.rows_written == 0

    # Sheet write and notification must NOT have been called again
    assert mock_sheets.append_call_count == 1
    assert len(mock_sheets.appended_rows) == 1
    assert mock_line.push_message.call_count == 1

    # 3. Third fulfillment via retry wrapper is also safely skipped
    res3 = fulfill_order_with_retry(
        order_id=order.id,
        db=db_session,
        sheets_client=mock_sheets,
        line_client_instance=mock_line,
    )
    assert res3.success is True
    assert res3.already_fulfilled is True
    assert mock_sheets.append_call_count == 1
    assert mock_line.push_message.call_count == 1


def test_non_payment_received_order_rejected_without_sheet_write(
    db_session: Session,
):
    """Orders not in PAYMENT_RECEIVED status cannot be fulfilled."""
    order = Order(
        id="ORD-DRAFT-001",
        shop_id="default",
        line_user_id="U_TEST",
        status=OrderStatus.AWAITING_PAYMENT.value,
        total=Decimal("100.00"),
        currency="THB",
    )
    db_session.add(order)
    db_session.commit()

    mock_sheets = MockSheetsClient()
    mock_line = MagicMock(spec=LineClient)

    with pytest.raises(InvalidOrderStateForFulfillmentError) as exc_info:
        fulfill_order(
            order_id=order.id,
            db=db_session,
            sheets_client=mock_sheets,
            line_client_instance=mock_line,
        )

    assert "AWAITING_PAYMENT" in str(exc_info.value)
    assert mock_sheets.append_call_count == 0
    assert mock_line.push_message.call_count == 0


def test_order_not_found_raises(db_session: Session):
    """Attempting to fulfill a non-existent order raises OrderNotFoundError."""
    mock_sheets = MockSheetsClient()
    mock_line = MagicMock(spec=LineClient)

    with pytest.raises(OrderNotFoundError):
        fulfill_order(
            order_id="NON-EXISTENT-ORD",
            db=db_session,
            sheets_client=mock_sheets,
            line_client_instance=mock_line,
        )


def test_exhausted_retries_leaves_order_in_payment_received_without_crash(
    db_session: Session,
    test_order_ready_for_fulfillment: Order,
):
    """
    When all retries are exhausted on SheetsAPIError:
    - Structured error is logged.
    - Order remains in PAYMENT_RECEIVED (not transitioned to FULFILLED).
    - Function returns failure result without crashing.
    - Zero notifications sent.
    """
    order = test_order_ready_for_fulfillment
    mock_sheets = MockSheetsClient()
    mock_sheets.fail_next_n_appends = 10  # Always fails
    mock_line = MagicMock(spec=LineClient)

    result = fulfill_order_with_retry(
        order_id=order.id,
        db=db_session,
        sheets_client=mock_sheets,
        line_client_instance=mock_line,
        max_attempts=3,
    )

    assert result.success is False
    assert result.status == OrderStatus.PAYMENT_RECEIVED.value
    assert "Fulfillment failed after 3 attempts" in result.message

    db_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_RECEIVED.value
    assert mock_sheets.append_call_count == 3
    assert len(mock_sheets.appended_rows) == 0
    assert mock_line.push_message.call_count == 0


def test_line_notification_failure_does_not_crash_fulfillment(
    db_session: Session,
    test_order_ready_for_fulfillment: Order,
):
    """
    If the LINE Messaging API push fails (network timeout, rate limit),
    the failure is logged, but the database commit and fulfillment result succeed.
    """
    order = test_order_ready_for_fulfillment
    mock_sheets = MockSheetsClient()
    mock_line = MagicMock(spec=LineClient)
    mock_line.push_message.side_effect = Exception("LINE Messaging API network timeout")

    result = fulfill_order(
        order_id=order.id,
        db=db_session,
        sheets_client=mock_sheets,
        line_client_instance=mock_line,
    )

    assert result.success is True
    db_session.refresh(order)
    assert order.status == OrderStatus.FULFILLED.value
    assert len(mock_sheets.appended_rows) == 1
    assert mock_line.push_message.call_count == 1


def test_fulfillment_sheet_row_matches_reference_schema(
    db_session: Session,
    test_order_ready_for_fulfillment: Order,
):
    """
    Verify sheet row schema matches reference_schema.md exactly:
    Order ID | Date | Receiver | Phone | Full Address | SKU | Product | Qty | Note | Paid | Tracking No.
    """
    order = test_order_ready_for_fulfillment
    mock_sheets = MockSheetsClient()
    mock_line = MagicMock(spec=LineClient)

    fulfill_order(
        order_id=order.id,
        db=db_session,
        sheets_client=mock_sheets,
        line_client_instance=mock_line,
    )

    assert len(mock_sheets.appended_rows) == 1
    row = mock_sheets.appended_rows[0]
    assert len(row) == 11

    # Check each column
    order_id, date, receiver, phone, full_addr, sku, product, qty, note, paid, tracking = row
    assert order_id == "ORD-PHASE9-001"
    assert receiver == "Somchai Jaidee"
    assert phone == "0812345678"
    assert "123/4 Sukhumvit Rd" in full_addr
    assert sku == "SKU-PHASE9-01"
    assert product == "Thai Silk Scarf Premium"
    assert qty == 1
    assert note == ""
    assert paid == "450.00"
    assert tracking == ""


def test_api_fulfill_endpoint(
    client: TestClient,
    db_session: Session,
    test_order_ready_for_fulfillment: Order,
):
    """Verify POST /api/orders/{order_id}/fulfill API endpoint."""
    from app.api.orders import get_line_client, get_sheets_client
    from app.main import app

    order = test_order_ready_for_fulfillment
    mock_sheets = MockSheetsClient()
    mock_line = MagicMock(spec=LineClient)

    app.dependency_overrides[get_sheets_client] = lambda: mock_sheets
    app.dependency_overrides[get_line_client] = lambda: mock_line

    try:
        # 1. Fulfill via API
        resp = client.post(f"/api/orders/{order.id}/fulfill")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["order_id"] == order.id
        assert data["status"] == OrderStatus.FULFILLED.value
        assert data["already_fulfilled"] is False
        assert mock_sheets.append_call_count == 1
        assert len(mock_sheets.appended_rows) == 1
        assert mock_line.push_message.call_count == 1

        # 2. Idempotent duplicate call returns 200 with already_fulfilled=True
        resp_dup = client.post(f"/api/orders/{order.id}/fulfill")
        assert resp_dup.status_code == 200
        data_dup = resp_dup.json()
        assert data_dup["already_fulfilled"] is True
        # Call counts remain unchanged
        assert mock_sheets.append_call_count == 1
        assert mock_line.push_message.call_count == 1

        # 3. Non-existent order returns 404
        resp_404 = client.post("/api/orders/NON-EXISTENT-ID/fulfill")
        assert resp_404.status_code == 404

        # 4. Order in invalid state returns 400
        draft_order = Order(
            id="ORD-DRAFT-API",
            shop_id="default",
            line_user_id="U_TEST",
            status=OrderStatus.ORDER_DRAFT.value,
            total=Decimal("100.00"),
            currency="THB",
        )
        db_session.add(draft_order)
        db_session.commit()

        resp_400 = client.post(f"/api/orders/{draft_order.id}/fulfill")
        assert resp_400.status_code == 400
    finally:
        app.dependency_overrides.pop(get_sheets_client, None)
        app.dependency_overrides.pop(get_line_client, None)


def test_schema_governance_no_extra_columns_or_tables(db_session: Session):
    """
    CRITICAL SCHEMA GOVERNANCE TEST (Verification Item 1):
    Asserts:
    1. 'orders' table contains ONLY columns defined in reference_schema.md.
       Specifically: NO 'synced_to_sheet' column.
    2. Database contains ONLY tables defined in reference_schema.md.
       Specifically: NO 'fulfillment_outbox' or 'sheet_outbox' tables.
    3. The FULFILLED status transition is the sole sync marker.
    """
    from pathlib import Path

    bind = db_session.get_bind()
    inspector = inspect(bind)

    # 1. Check orders columns
    columns = {col["name"] for col in inspector.get_columns("orders")}
    expected_orders_columns = {
        "id",
        "shop_id",
        "line_user_id",
        "status",
        "total",
        "currency",
        "created_at",
        "updated_at",
        "ttl_expires_at",
        "approval_state",
        "payment_ref",
        "risk_score",
    }
    assert columns == expected_orders_columns, (
        f"Columns on 'orders' table do not match reference_schema.md. "
        f"Extra columns: {columns - expected_orders_columns}, Missing: {expected_orders_columns - columns}"
    )
    assert "synced_to_sheet" not in columns

    # 2. Check table names
    table_names = set(inspector.get_table_names())
    forbidden_tables = {"fulfillment_outbox", "sheet_outbox", "order_outbox"}
    assert table_names.isdisjoint(forbidden_tables), (
        f"Forbidden tables detected in database: {table_names & forbidden_tables}"
    )

    # 3. Verify migration file has no forbidden columns or tables
    migration_path = (
        Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0008_phase9_fulfillment.py"
    )
    assert migration_path.exists(), f"Migration file not found at {migration_path}"
    with open(migration_path, encoding="utf-8") as f:
        migration_code = f.read()
    assert "create_table" not in migration_code
    assert "add_column" not in migration_code
    assert "synced_to_sheet" not in migration_code
    assert "fulfillment_outbox" not in migration_code
    assert "synced_to_sheet" not in migration_code
    assert "fulfillment_outbox" not in migration_code
