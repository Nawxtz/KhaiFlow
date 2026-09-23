import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.inventory import Inventory
from app.models.order import Order, OrderItem, OrderStatus
from app.models.payment import ConsumedPaymentClaim, PaymentEvent
from app.services.payment_trigger import process_payment_trigger
from app.services.reservation_service import reserve_order_stock
from tests.conftest import TestingSessionLocal


def seed_order_awaiting_payment(order_id: str, sku: str = "IDEMP-SKU-001") -> Order:
    """Helper to seed an order in AWAITING_PAYMENT state with stock reserved."""
    with TestingSessionLocal() as session:
        inv = Inventory(
            sku=sku,
            shop_id="default",
            name="Idempotency Test Item",
            category="Home",
            price=Decimal("400.00"),
            stock=10,
            reserved=0,
            active=True,
            version=1,
        )
        order = Order(
            id=order_id,
            shop_id="default",
            line_user_id="user_idemp",
            status=OrderStatus.ADDRESS_CONFIRMED.value,
            total=Decimal("400.00"),
            currency="THB",
        )
        item = OrderItem(
            order_id=order.id,
            shop_id="default",
            sku=sku,
            name="Idempotency Test Item",
            qty=1,
            unit_price=Decimal("400.00"),
            line_total=Decimal("400.00"),
        )
        session.add_all([inv, order, item])
        session.commit()

        # Reserve stock
        reserved_order = reserve_order_stock(
            db=session,
            order_id=order_id,
            shop_id="default",
            ttl_seconds=600,
        )
        return reserved_order


def test_first_trigger_processes_and_stops_ttl():
    """
    First payment trigger processes successfully, records claim, and stops TTL.
    """
    order_id = "ORD-IDEMP-001"
    seed_order_awaiting_payment(order_id=order_id)

    claim_key = "ref:TXN-20260923-0001"

    with TestingSessionLocal() as session:
        result = process_payment_trigger(
            db=session,
            claim_key=claim_key,
            order_id=order_id,
            shop_id="default",
            channel="webhook",
            payload_json={"provider": "mock_bank", "amount": "400.00"},
        )

        assert result.status == "processed"
        assert result.is_duplicate is False
        assert result.claim_key == claim_key

        # Verify claim was inserted into consumed_payment_claims
        claim = session.execute(
            select(ConsumedPaymentClaim).where(ConsumedPaymentClaim.claim_key == claim_key)
        ).scalar_one()
        assert claim.order_id == order_id
        assert claim.state == "CONFIRMED"

        # Verify payment event was recorded
        event = session.execute(
            select(PaymentEvent).where(PaymentEvent.event_key == f"evt_{claim_key}")
        ).scalar_one()
        assert event.order_id == order_id
        assert event.event_type == "PAYMENT_TRIGGER"

        # Verify order transitioned to PAYMENT_RECEIVED and TTL is stopped
        order = session.execute(select(Order).where(Order.id == order_id)).scalar_one()
        assert order.status == OrderStatus.PAYMENT_RECEIVED.value
        assert order.ttl_expires_at is None


def test_duplicate_trigger_is_idempotent_no_double_processing():
    """
    TEST_PLAN.md: Same trigger received twice is idempotent - no double-processing.
    The second trigger attempt with the exact same claim_key:
    - Returns duplicate status (is_duplicate=True).
    - Does NOT raise UniqueConstraintError to the caller.
    - Leaves consumed_payment_claims with exactly 1 row.
    """
    order_id = "ORD-IDEMP-002"
    seed_order_awaiting_payment(order_id=order_id)
    claim_key = "ref:TXN-20260923-0002"

    with TestingSessionLocal() as session:
        # First delivery
        first_result = process_payment_trigger(
            db=session,
            claim_key=claim_key,
            order_id=order_id,
            shop_id="default",
        )
        assert first_result.is_duplicate is False
        assert first_result.status == "processed"

        # Duplicate delivery (e.g. gateway network retry)
        second_result = process_payment_trigger(
            db=session,
            claim_key=claim_key,
            order_id=order_id,
            shop_id="default",
        )
        assert second_result.is_duplicate is True
        assert second_result.status == "duplicate"

        # Verify only one claim exists in database
        count = session.execute(
            select(func.count(ConsumedPaymentClaim.id)).where(
                ConsumedPaymentClaim.claim_key == claim_key
            )
        ).scalar_one()
        assert count == 1


def test_concurrent_identical_triggers_exactly_one_claim_inserted():
    """
    Two concurrent threads sending the exact same trigger simultaneously.
    - Real PostgreSQL concurrency.
    - Exactly 1 thread inserts the claim.
    - The other thread gets clean duplicate status.
    - Neither thread crashes or raises unhandled database errors.
    """
    order_id = "ORD-IDEMP-CONC"
    seed_order_awaiting_payment(order_id=order_id)
    claim_key = "ref:TXN-CONCURRENT-001"

    barrier = threading.Barrier(2)
    results: list[dict[str, object]] = []
    lock = threading.Lock()

    def send_trigger(idx: int) -> None:
        barrier.wait()
        with TestingSessionLocal() as session:
            try:
                res = process_payment_trigger(
                    db=session,
                    claim_key=claim_key,
                    order_id=order_id,
                    shop_id="default",
                )
                with lock:
                    results.append({"idx": idx, "success": True, "result": res})
            except Exception as exc:
                with lock:
                    results.append({"idx": idx, "success": False, "error": exc})

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(send_trigger, 1)
        f2 = executor.submit(send_trigger, 2)
        f1.result()
        f2.result()

    assert len(results) == 2
    for r in results:
        assert r["success"] is True

    processed = [r for r in results if r["result"].is_duplicate is False]
    duplicates = [r for r in results if r["result"].is_duplicate is True]

    assert len(processed) == 1
    assert len(duplicates) == 1

    with TestingSessionLocal() as session:
        claims = list(
            session.execute(
                select(ConsumedPaymentClaim).where(ConsumedPaymentClaim.claim_key == claim_key)
            )
            .scalars()
            .all()
        )
        assert len(claims) == 1


def test_api_payment_trigger_endpoint_idempotency(client: TestClient):
    """
    Test /api/payment/trigger endpoint:
    - Initial webhook delivery returns 200 with is_duplicate=False.
    - Retried delivery returns 200 with is_duplicate=True.
    """
    order_id = "ORD-API-TRIGGER-001"
    seed_order_awaiting_payment(order_id=order_id)
    claim_key = "ref:API-TXN-999"

    # First call
    res1 = client.post(
        "/api/payment/trigger",
        json={
            "claim_key": claim_key,
            "order_id": order_id,
            "shop_id": "default",
            "channel": "webhook",
            "payload": {"source": "gateway_webhook"},
        },
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "processed"
    assert data1["is_duplicate"] is False

    # Second call with same claim_key
    res2 = client.post(
        "/api/payment/trigger",
        json={
            "claim_key": claim_key,
            "order_id": order_id,
            "shop_id": "default",
            "channel": "webhook",
            "payload": {"source": "gateway_webhook"},
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "duplicate"
    assert data2["is_duplicate"] is True
