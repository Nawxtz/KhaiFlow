import inspect
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.line_client import LineClient
from app.models.inventory import Inventory
from app.models.order import Order, OrderItem, OrderStatus
from app.models.payment import PaymentEvent, Reservation
from app.services.gateway_webhook_service import (
    compute_gateway_signature,
    process_gateway_webhook,
)

TEST_SECRET = "test_gateway_webhook_secret_key_123"


@pytest.fixture(autouse=True)
def set_gateway_secret(monkeypatch):
    """Ensure GATEWAY_WEBHOOK_SECRET is set for tests."""
    monkeypatch.setattr(settings, "GATEWAY_WEBHOOK_SECRET", TEST_SECRET)


class MockTrackingLineClient(LineClient):
    """Test LineClient spy tracking outbound calls."""

    def __init__(self):
        super().__init__()
        self.sent_messages: list[tuple[str, str]] = []
        self.pushed_messages: list[tuple[str, Any]] = []

    def send_message(self, to: str, text: str) -> None:
        self.sent_messages.append((to, text))

    def push_message(self, to: str, messages: Any) -> None:
        self.pushed_messages.append((to, messages))


# -----------------------------------------------------------------------------
# Acceptance Criterion 1 & Reviewer Item 4:
# Valid Webhook -> Order Transitions to PAYMENT_RECEIVED, Stock and Reserved Decremented Atomically
# -----------------------------------------------------------------------------
def test_valid_gateway_webhook_confirms_payment_and_decrements_stock_atomically(
    client: TestClient,
    db_session: Session,
):
    """
    TEST_PLAN.md Phase 8:
    Valid webhook -> order transitions to PAYMENT_RECEIVED; stock and reserved decremented atomically.
    """
    # 1. Setup inventory: initial physical stock = 10, reserved = 2 (available = 8)
    item = Inventory(
        sku="SKU-GW-001",
        shop_id="shop_test",
        name="Thai Silk Scarf",
        category="Fashion",
        price=Decimal("450.00"),
        stock=10,
        reserved=2,
        active=True,
        version=1,
    )
    db_session.add(item)

    # 2. Setup order in AWAITING_PAYMENT with line item qty=2
    order = Order(
        id="ord_phase8_001",
        shop_id="shop_test",
        line_user_id="U_test_buyer_8",
        status=OrderStatus.AWAITING_PAYMENT.value,
        total=Decimal("900.00"),
        currency="THB",
        ttl_expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(order)

    order_item = OrderItem(
        order_id="ord_phase8_001",
        shop_id="shop_test",
        sku="SKU-GW-001",
        name="Thai Silk Scarf",
        qty=2,
        unit_price=Decimal("450.00"),
        line_total=Decimal("900.00"),
    )
    db_session.add(order_item)

    reservation = Reservation(
        order_id="ord_phase8_001",
        shop_id="shop_test",
        sku="SKU-GW-001",
        qty=2,
        state="RESERVED",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(reservation)
    db_session.commit()

    # 3. Construct and sign gateway webhook payload
    payload = {
        "event_key": "evt_gateway_tx_1001",
        "order_id": "ord_phase8_001",
        "amount": "900.00",
        "currency": "THB",
        "status": "SUCCESS",
        "transaction_id": "tx_omise_12345",
        "shop_id": "shop_test",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_gateway_signature(raw_body, TEST_SECRET)

    # 4. Send request to endpoint
    response = client.post(
        "/api/gateway/webhook",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Gateway-Signature": sig,
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == OrderStatus.PAYMENT_RECEIVED.value
    assert data["is_duplicate"] is False
    assert data["order_id"] == "ord_phase8_001"

    # 5. Verify database changes:
    # Order transitioned to PAYMENT_RECEIVED, TTL cleared
    db_session.expire_all()
    updated_order = db_session.get(Order, "ord_phase8_001")
    assert updated_order is not None
    assert updated_order.status == OrderStatus.PAYMENT_RECEIVED.value
    assert updated_order.ttl_expires_at is None
    assert updated_order.payment_ref == "tx_omise_12345"

    # Inventory stock and reserved atomically decremented by 2
    updated_inv = db_session.get(Inventory, "SKU-GW-001")
    assert updated_inv is not None
    assert updated_inv.stock == 8  # 10 - 2
    assert updated_inv.reserved == 0  # 2 - 2

    # Reservation state flipped to CONFIRMED
    updated_res = db_session.execute(
        select(Reservation).where(Reservation.order_id == "ord_phase8_001")
    ).scalar_one()
    assert updated_res.state == "CONFIRMED"

    # Exactly 1 payment_events row created with decision CONFIRMED
    events = list(
        db_session.execute(
            select(PaymentEvent).where(PaymentEvent.event_key == "evt_gateway_tx_1001")
        ).scalars().all()
    )
    assert len(events) == 1
    assert events[0].decision == "CONFIRMED"


# -----------------------------------------------------------------------------
# Acceptance Criterion 2 & Reviewer Item 2 & 4:
# Duplicate Webhook (Same event_key) -> Idempotent; Inventory EXACTLY Unchanged; No Double Decrement
# -----------------------------------------------------------------------------
def test_duplicate_webhook_is_idempotent_and_does_not_double_decrement(
    client: TestClient,
    db_session: Session,
):
    """
    CRITICAL Reviewer Item 2 & 4:
    - Send webhook 1 -> verify inventory.stock decreased by qty, inventory.reserved decreased by qty.
    - Record exact stock and reserved values.
    - Send identical webhook 2 (same event_key).
    - Query inventory again and assert stock and reserved are EXACTLY the same values as recorded after webhook 1.
    - Assert payment_events table has exactly 1 row for that event_key.
    """
    # 1. Setup inventory: stock = 20, reserved = 3 (available = 17)
    item = Inventory(
        sku="SKU-GW-002",
        shop_id="shop_test",
        name="Handmade Clay Mug",
        category="Home",
        price=Decimal("280.00"),
        stock=20,
        reserved=3,
        active=True,
        version=1,
    )
    db_session.add(item)

    # 2. Setup order in AWAITING_PAYMENT with qty = 3
    order = Order(
        id="ord_phase8_002",
        shop_id="shop_test",
        line_user_id="U_test_buyer_8",
        status=OrderStatus.AWAITING_PAYMENT.value,
        total=Decimal("840.00"),
        currency="THB",
        ttl_expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(order)

    order_item = OrderItem(
        order_id="ord_phase8_002",
        shop_id="shop_test",
        sku="SKU-GW-002",
        name="Handmade Clay Mug",
        qty=3,
        unit_price=Decimal("280.00"),
        line_total=Decimal("840.00"),
    )
    db_session.add(order_item)

    reservation = Reservation(
        order_id="ord_phase8_002",
        shop_id="shop_test",
        sku="SKU-GW-002",
        qty=3,
        state="RESERVED",
    )
    db_session.add(reservation)
    db_session.commit()

    # 3. Payload with distinct event_key
    payload = {
        "event_key": "evt_unique_bank_ref_778899",
        "order_id": "ord_phase8_002",
        "amount": "840.00",
        "currency": "THB",
        "status": "SUCCESS",
        "transaction_id": "bank_tx_778899",
        "shop_id": "shop_test",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_gateway_signature(raw_body, TEST_SECRET)

    # 4. SEND WEBHOOK 1
    resp1 = client.post(
        "/api/gateway/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Gateway-Signature": sig},
    )
    assert resp1.status_code == 200
    assert resp1.json()["is_duplicate"] is False

    # Verify inventory decremented after webhook 1
    db_session.expire_all()
    inv_after_1 = db_session.get(Inventory, "SKU-GW-002")
    assert inv_after_1 is not None
    assert inv_after_1.stock == 17  # 20 - 3
    assert inv_after_1.reserved == 0  # 3 - 3

    # RECORD EXACT VALUES
    recorded_stock = inv_after_1.stock
    recorded_reserved = inv_after_1.reserved
    assert recorded_stock == 17
    assert recorded_reserved == 0

    # Verify payment_events after webhook 1
    events_after_1 = list(
        db_session.execute(
            select(PaymentEvent).where(PaymentEvent.event_key == "evt_unique_bank_ref_778899")
        ).scalars().all()
    )
    assert len(events_after_1) == 1

    # 5. SEND IDENTICAL WEBHOOK 2 (same event_key)
    resp2 = client.post(
        "/api/gateway/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Gateway-Signature": sig},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_duplicate"] is True
    assert data2["status"] == "DUPLICATE"

    # 6. ASSERT INVENTORY VALUES ARE EXACTLY UNCHANGED
    db_session.expire_all()
    inv_after_2 = db_session.get(Inventory, "SKU-GW-002")
    assert inv_after_2 is not None
    assert inv_after_2.stock == recorded_stock, f"Expected stock {recorded_stock}, got {inv_after_2.stock}"
    assert inv_after_2.reserved == recorded_reserved, f"Expected reserved {recorded_reserved}, got {inv_after_2.reserved}"

    # 7. ASSERT PAYMENT_EVENTS TABLE HAS EXACTLY 1 ROW
    events_after_2 = list(
        db_session.execute(
            select(PaymentEvent).where(PaymentEvent.event_key == "evt_unique_bank_ref_778899")
        ).scalars().all()
    )
    assert len(events_after_2) == 1, f"Expected 1 payment event, found {len(events_after_2)}"


# -----------------------------------------------------------------------------
# Acceptance Criterion 3 & Reviewer Item 1:
# Confirm-Time Decrement Fails (rowcount == 0) -> Transitions to PAYMENT_RECONCILE
# -----------------------------------------------------------------------------
def test_confirm_time_decrement_rowcount_zero_routes_to_payment_reconcile(
    client: TestClient,
    db_session: Session,
    caplog,
):
    """
    CRITICAL Reviewer Item 1:
    - Simulates lost stock: inventory stock has dropped below requested quantity
      (e.g. via TTL race or manual override).
    - Resulting UPDATE rowcount == 0.
    - Explicitly routes to PAYMENT_RECONCILE.
    - Does NOT raise an exception.
    - Does NOT leave order in AWAITING_PAYMENT.
    - Does NOT silently ignore.
    - Keeps reservation hold intact.
    - Logs structured warning with order_id for ops visibility.
    """
    # 1. Setup inventory with corrupted/lost stock (stock = 0, reserved = 0)
    # But order needs qty = 2!
    item = Inventory(
        sku="SKU-GW-LOST",
        shop_id="shop_test",
        name="Lost Stock Product",
        category="Electronics",
        price=Decimal("1200.00"),
        stock=0,  # Stock was lost or overridden!
        reserved=0,  # Reserved was lost!
        active=True,
        version=1,
    )
    db_session.add(item)

    order = Order(
        id="ord_phase8_reconcile_003",
        shop_id="shop_test",
        line_user_id="U_test_buyer_reconcile",
        status=OrderStatus.AWAITING_PAYMENT.value,
        total=Decimal("2400.00"),
        currency="THB",
        ttl_expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(order)

    order_item = OrderItem(
        order_id="ord_phase8_reconcile_003",
        shop_id="shop_test",
        sku="SKU-GW-LOST",
        name="Lost Stock Product",
        qty=2,
        unit_price=Decimal("1200.00"),
        line_total=Decimal("2400.00"),
    )
    db_session.add(order_item)

    reservation = Reservation(
        order_id="ord_phase8_reconcile_003",
        shop_id="shop_test",
        sku="SKU-GW-LOST",
        qty=2,
        state="RESERVED",
    )
    db_session.add(reservation)
    db_session.commit()

    # 2. Webhook payload
    payload = {
        "event_key": "evt_lost_stock_case_001",
        "order_id": "ord_phase8_reconcile_003",
        "amount": "2400.00",
        "currency": "THB",
        "status": "SUCCESS",
        "transaction_id": "tx_reconcile_999",
        "shop_id": "shop_test",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_gateway_signature(raw_body, TEST_SECRET)

    # 3. Post webhook with dedicated log handler to reliably capture structured warning
    log_records: list[logging.LogRecord] = []

    class DedicatedLogHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_records.append(record)

    webhook_logger = logging.getLogger("app.services.gateway_webhook_service")
    webhook_logger.disabled = False
    webhook_logger.setLevel(logging.WARNING)
    handler = DedicatedLogHandler()
    webhook_logger.addHandler(handler)
    try:
        resp = client.post(
            "/api/gateway/webhook",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Gateway-Signature": sig},
        )
    finally:
        webhook_logger.removeHandler(handler)

    # Must return 200 HTTP without crashing (status describes reconcile)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == OrderStatus.PAYMENT_RECONCILE.value
    assert data["order_status"] == OrderStatus.PAYMENT_RECONCILE.value

    # 4. Verify database state
    db_session.expire_all()
    updated_order = db_session.get(Order, "ord_phase8_reconcile_003")
    assert updated_order is not None
    # Crucial assertion: NOT AWAITING_PAYMENT, NOT PAYMENT_RECEIVED, MUST BE PAYMENT_RECONCILE
    assert updated_order.status == OrderStatus.PAYMENT_RECONCILE.value
    assert updated_order.approval_state == "RECONCILE_REQUIRED"
    assert updated_order.ttl_expires_at is None

    # Crucial assertion: Hold kept! Reservation row is STILL RESERVED (not CONFIRMED, not RELEASED)
    res_after = db_session.execute(
        select(Reservation).where(Reservation.order_id == "ord_phase8_reconcile_003")
    ).scalar_one()
    assert res_after.state == "RESERVED"

    # Crucial assertion: Inventory stock was not decremented below zero
    inv_after = db_session.get(Inventory, "SKU-GW-LOST")
    assert inv_after is not None
    assert inv_after.stock == 0
    assert inv_after.reserved == 0

    # Crucial assertion: Structured ops warning was logged with order_id
    captured_messages = [record.getMessage() for record in log_records]
    assert any("ord_phase8_reconcile_003" in msg for msg in captured_messages)
    assert any("PAYMENT_RECONCILE" in msg for msg in captured_messages)


# -----------------------------------------------------------------------------
# Acceptance Criterion 4 & Reviewer Item 3:
# Signature Verified BEFORE Any DB Query or Payload Parse
# -----------------------------------------------------------------------------
def test_webhook_invalid_signature_rejected_before_db_or_payload_parse(
    client: TestClient,
    db_session: Session,
):
    """
    CRITICAL Reviewer Item 3:
    The signature verification test must verify that an invalid-signature request:
    - Returns HTTP 400.
    - Results in zero new rows in payment_events.
    - Results in zero changes to any order or inventory row.
    """
    # 1. Existing order in DB to ensure it is NOT touched
    order = Order(
        id="ord_phase8_sig_test",
        line_user_id="U_attacker_victim",
        status=OrderStatus.AWAITING_PAYMENT.value,
        total=Decimal("500.00"),
    )
    db_session.add(order)
    db_session.commit()

    # Initial counts
    events_count_before = db_session.execute(select(PaymentEvent)).scalars().all()

    # 2. Forged payload with invalid signature
    payload = {
        "event_key": "evt_forged_signature_001",
        "order_id": "ord_phase8_sig_test",
        "amount": "500.00",
        "status": "SUCCESS",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    invalid_sig = "bad_forged_hmac_signature_hex_1234567890abcdef"

    # 3. Post to endpoint
    resp = client.post(
        "/api/gateway/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Gateway-Signature": invalid_sig},
    )

    # MUST return HTTP 400
    assert resp.status_code == 400

    # 4. Zero new rows in payment_events
    events_count_after = db_session.execute(select(PaymentEvent)).scalars().all()
    assert len(events_count_after) == len(events_count_before)

    # 5. Zero changes to order
    db_session.expire_all()
    ord_after = db_session.get(Order, "ord_phase8_sig_test")
    assert ord_after is not None
    assert ord_after.status == OrderStatus.AWAITING_PAYMENT.value


def test_signature_verification_executes_zero_db_queries_on_invalid_signature(
    client: TestClient,
):
    """
    SECURITY.md: Proves zero DB queries execute when signature fails.
    Attaches a query listener to the SQLAlchemy engine.
    """
    from tests.conftest import test_engine

    queries: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(test_engine, "before_cursor_execute", before_cursor_execute)
    try:
        raw_body = b'{"event_key": "evt_timing_probe", "order_id": "ord_timing"}'
        resp = client.post(
            "/api/gateway/webhook",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Gateway-Signature": "invalid_signature_hex",
            },
        )
        assert resp.status_code == 400
        # Exactly 0 queries must have hit the database during this unauthenticated request
        assert len(queries) == 0, f"Expected 0 queries, executed: {queries}"
    finally:
        event.remove(test_engine, "before_cursor_execute", before_cursor_execute)


def test_webhook_missing_signature_header_rejected_immediately(client: TestClient):
    """Missing X-Gateway-Signature header must immediately return HTTP 400."""
    raw_body = b'{"event_key": "evt_no_sig", "order_id": "ord_no_sig"}'
    resp = client.post(
        "/api/gateway/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert "signature" in resp.text.lower()


# -----------------------------------------------------------------------------
# Static Code Audit & Zero SELECT Before INSERT
# -----------------------------------------------------------------------------
def test_gateway_webhook_idempotency_has_zero_select_before_insert():
    """
    Reviewer Item 2: Code-level verification that idempotency check in
    process_gateway_webhook executes zero SELECT queries on payment_events
    before the atomic INSERT ON CONFLICT DO NOTHING.
    """
    source = inspect.getsource(process_gateway_webhook)

    # Locate the Step 3 INSERT statement
    insert_pos = source.find("INSERT INTO payment_events")
    assert insert_pos != -1, "process_gateway_webhook must contain INSERT INTO payment_events"

    code_before_insert = source[:insert_pos]

    # Must NOT contain select(PaymentEvent) or SELECT FROM payment_events before the insert
    assert "select(PaymentEvent)" not in code_before_insert
    assert "FROM payment_events" not in code_before_insert
    assert "payment_events" not in code_before_insert


def test_explicit_rowcount_zero_block_exists_in_service_source():
    """
    Reviewer Item 1: Static code audit confirming explicit
    'if result.rowcount == 0:' block routing to PAYMENT_RECONCILE exists in
    gateway_webhook_service.py.
    """
    source = inspect.getsource(process_gateway_webhook)
    assert "if result.rowcount == 0:" in source or "if result.rowcount != 1:" in source
    assert "OrderStatus.PAYMENT_RECONCILE.value" in source
    assert "order.status = OrderStatus.PAYMENT_RECONCILE.value" in source


# -----------------------------------------------------------------------------
# Additional Resilience: Malformed Payload & Delayed Webhooks
# -----------------------------------------------------------------------------
def test_malformed_webhook_payload_rejected_without_crash(client: TestClient):
    """
    TEST_PLAN.md: Malformed webhook payload is rejected without crashing.
    Valid signature over bad JSON body -> HTTP 400.
    """
    bad_body = b"NOT_VALID_JSON{:::broken"
    sig = compute_gateway_signature(bad_body, TEST_SECRET)

    resp = client.post(
        "/api/gateway/webhook",
        content=bad_body,
        headers={"Content-Type": "application/json", "X-Gateway-Signature": sig},
    )

    assert resp.status_code == 400
    assert "malformed" in resp.text.lower() or "json" in resp.text.lower()


def test_delayed_webhook_arriving_after_ttl_handled_safely(
    client: TestClient,
    db_session: Session,
):
    """
    TEST_PLAN.md: Delayed webhook (arrives after TTL) is handled safely.
    If stock is still held, payment is confirmed and TTL is cleared.
    """
    item = Inventory(
        sku="SKU-GW-DELAY",
        name="Delayed Item",
        price=Decimal("100.00"),
        stock=5,
        reserved=1,
        active=True,
    )
    db_session.add(item)

    # Order where ttl_expires_at is 1 hour in the past
    past_time = datetime.now(UTC) - timedelta(hours=1)
    order = Order(
        id="ord_phase8_delayed_004",
        line_user_id="U_test_delayed",
        status=OrderStatus.AWAITING_PAYMENT.value,
        total=Decimal("100.00"),
        ttl_expires_at=past_time,
    )
    db_session.add(order)

    order_item = OrderItem(
        order_id="ord_phase8_delayed_004",
        sku="SKU-GW-DELAY",
        name="Delayed Item",
        qty=1,
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
    )
    db_session.add(order_item)

    res = Reservation(
        order_id="ord_phase8_delayed_004",
        sku="SKU-GW-DELAY",
        qty=1,
        state="RESERVED",
    )
    db_session.add(res)
    db_session.commit()

    payload = {
        "event_key": "evt_delayed_order_123",
        "order_id": "ord_phase8_delayed_004",
        "amount": "100.00",
        "status": "SUCCESS",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_gateway_signature(raw_body, TEST_SECRET)

    resp = client.post(
        "/api/gateway/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Gateway-Signature": sig},
    )

    assert resp.status_code == 200
    db_session.expire_all()
    ord_after = db_session.get(Order, "ord_phase8_delayed_004")
    assert ord_after is not None
    assert ord_after.status == OrderStatus.PAYMENT_RECEIVED.value
    assert ord_after.ttl_expires_at is None


def test_buyer_notification_called_on_payment_confirmation(db_session: Session):
    """Verify buyer is notified via line_client on payment confirmation."""
    item = Inventory(
        sku="SKU-GW-NOTIFY",
        name="Notify Item",
        price=Decimal("100.00"),
        stock=5,
        reserved=1,
        active=True,
    )
    db_session.add(item)

    order = Order(
        id="ord_phase8_notify_005",
        line_user_id="U_buyer_notify_line",
        status=OrderStatus.AWAITING_PAYMENT.value,
        total=Decimal("100.00"),
    )
    db_session.add(order)
    order_item = OrderItem(
        order_id="ord_phase8_notify_005",
        sku="SKU-GW-NOTIFY",
        name="Notify Item",
        qty=1,
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
    )
    db_session.add(order_item)
    db_session.commit()

    payload = {
        "event_key": "evt_notify_test_001",
        "order_id": "ord_phase8_notify_005",
        "amount": "100.00",
        "status": "SUCCESS",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_gateway_signature(raw_body, TEST_SECRET)

    line_spy = MockTrackingLineClient()
    result = process_gateway_webhook(
        raw_body=raw_body,
        signature=sig,
        db=db_session,
        secret=TEST_SECRET,
        line_client_instance=line_spy,
    )

    assert result.status == OrderStatus.PAYMENT_RECEIVED.value
    assert len(line_spy.sent_messages) == 1
    recipient, msg_text = line_spy.sent_messages[0]
    assert recipient == "U_buyer_notify_line"
    assert "ord_phase8_notify_005" in msg_text
