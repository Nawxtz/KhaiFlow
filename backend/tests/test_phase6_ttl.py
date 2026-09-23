from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models.inventory import Inventory
from app.models.order import Order, OrderItem, OrderStatus
from app.models.payment import Reservation
from app.services.payment_trigger import process_payment_trigger
from app.services.reservation_service import (
    expire_stale_reservations,
    reserve_order_stock,
    reserve_stock,
)
from tests.conftest import TestingSessionLocal


def seed_inventory(
    sku: str,
    stock: int = 5,
    reserved: int = 0,
    price: Decimal = Decimal("300.00"),
) -> None:
    """Seed inventory record."""
    with TestingSessionLocal() as session:
        item = Inventory(
            sku=sku,
            shop_id="default",
            name=f"Product {sku}",
            category="Home",
            price=price,
            stock=stock,
            reserved=reserved,
            active=True,
            version=1,
        )
        session.add(item)
        session.commit()


def test_ttl_expiry_restores_available_stock_using_injected_now_fn():
    """
    TEST_PLAN.md: TTL expiry releases the reservation when no payment trigger arrives.
    Time travel is achieved by injecting now_fn into expire_stale_reservations.
    """
    sku = "TTL-SKU-001"
    seed_inventory(sku=sku, stock=5, reserved=0)

    base_time = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)

    # 1. Create order and reserve stock
    with TestingSessionLocal() as session:
        order = Order(
            id="ORD-TTL-001",
            shop_id="default",
            line_user_id="user_ttl_1",
            status=OrderStatus.ADDRESS_CONFIRMED.value,
            total=Decimal("600.00"),
            currency="THB",
        )
        item = OrderItem(
            order_id=order.id,
            shop_id="default",
            sku=sku,
            name="TTL Product",
            qty=2,
            unit_price=Decimal("300.00"),
            line_total=Decimal("600.00"),
        )
        session.add_all([order, item])
        session.commit()

        # Reserve order with injected now_fn and 600s TTL
        reserve_order_stock(
            db=session,
            order_id=order.id,
            shop_id="default",
            now_fn=lambda: base_time,
            ttl_seconds=600,
        )

    # Verify initial reservation state
    with TestingSessionLocal() as session:
        inv = session.execute(select(Inventory).where(Inventory.sku == sku)).scalar_one()
        assert inv.reserved == 2
        assert (inv.stock - inv.reserved) == 3

        ord_record = session.execute(select(Order).where(Order.id == "ORD-TTL-001")).scalar_one()
        assert ord_record.status == OrderStatus.AWAITING_PAYMENT.value
        assert ord_record.ttl_expires_at == base_time + timedelta(seconds=600)

        res = session.execute(
            select(Reservation).where(Reservation.order_id == "ORD-TTL-001")
        ).scalar_one()
        assert res.state == "RESERVED"

    # 2. Check before expiry (e.g. at T+300s) -> should NOT expire
    t_mid = base_time + timedelta(seconds=300)
    with TestingSessionLocal() as session:
        expired_ids = expire_stale_reservations(db=session, now_fn=lambda: t_mid)
        assert len(expired_ids) == 0

        # Stock is still reserved
        inv = session.execute(select(Inventory).where(Inventory.sku == sku)).scalar_one()
        assert inv.reserved == 2

    # 3. Check after expiry (e.g. at T+601s) -> MUST expire and release stock
    t_after = base_time + timedelta(seconds=601)
    with TestingSessionLocal() as session:
        expired_ids = expire_stale_reservations(db=session, now_fn=lambda: t_after)
        assert "ORD-TTL-001" in expired_ids

        # Verify order transitioned to RESERVATION_EXPIRED
        ord_record = session.execute(select(Order).where(Order.id == "ORD-TTL-001")).scalar_one()
        assert ord_record.status == OrderStatus.RESERVATION_EXPIRED.value
        assert ord_record.ttl_expires_at is None

        # Verify stock restored: reserved is back to 0, available is 5
        inv = session.execute(select(Inventory).where(Inventory.sku == sku)).scalar_one()
        assert inv.reserved == 0
        assert (inv.stock - inv.reserved) == 5

        # Verify reservation record state is RELEASED
        res = session.execute(
            select(Reservation).where(Reservation.order_id == "ORD-TTL-001")
        ).scalar_one()
        assert res.state == "RELEASED"


def test_any_trigger_stops_the_ttl():
    """
    TEST_PLAN.md: Any trigger stops the TTL.
    When a payment trigger is received, the order transitions from AWAITING_PAYMENT to PAYMENT_RECEIVED.
    When the TTL background job runs after the original expiry time, it must NOT release the reservation.
    """
    sku = "TTL-SKU-002"
    seed_inventory(sku=sku, stock=10, reserved=0)

    base_time = datetime(2026, 9, 23, 14, 0, 0, tzinfo=UTC)

    # 1. Create order and reserve stock
    with TestingSessionLocal() as session:
        order = Order(
            id="ORD-TRIGGER-001",
            shop_id="default",
            line_user_id="user_trigger_1",
            status=OrderStatus.ADDRESS_CONFIRMED.value,
            total=Decimal("900.00"),
            currency="THB",
        )
        item = OrderItem(
            order_id=order.id,
            shop_id="default",
            sku=sku,
            name="Trigger Test Item",
            qty=3,
            unit_price=Decimal("300.00"),
            line_total=Decimal("900.00"),
        )
        session.add_all([order, item])
        session.commit()

        reserve_order_stock(
            db=session,
            order_id=order.id,
            shop_id="default",
            now_fn=lambda: base_time,
            ttl_seconds=600,
        )

    # Verify order is AWAITING_PAYMENT with reserved=3
    with TestingSessionLocal() as session:
        inv = session.execute(select(Inventory).where(Inventory.sku == sku)).scalar_one()
        assert inv.reserved == 3

    # 2. Payment trigger arrives before expiry
    with TestingSessionLocal() as session:
        result = process_payment_trigger(
            db=session,
            claim_key="ref:TXN-STOP-TTL-001",
            order_id="ORD-TRIGGER-001",
            shop_id="default",
        )
        assert result.status == "processed"
        assert result.is_duplicate is False

        # Order status should now be PAYMENT_RECEIVED and ttl_expires_at is None
        ord_record = session.execute(
            select(Order).where(Order.id == "ORD-TRIGGER-001")
        ).scalar_one()
        assert ord_record.status == OrderStatus.PAYMENT_RECEIVED.value
        assert ord_record.ttl_expires_at is None

    # 3. Fast-forward time past original TTL (T+1000s) and run TTL expiry job
    t_far_future = base_time + timedelta(seconds=1000)
    with TestingSessionLocal() as session:
        expired_ids = expire_stale_reservations(db=session, now_fn=lambda: t_far_future)
        assert "ORD-TRIGGER-001" not in expired_ids

        # Order must remain PAYMENT_RECEIVED
        ord_record = session.execute(
            select(Order).where(Order.id == "ORD-TRIGGER-001")
        ).scalar_one()
        assert ord_record.status == OrderStatus.PAYMENT_RECEIVED.value

        # Reserved stock must NOT be released!
        inv = session.execute(select(Inventory).where(Inventory.sku == sku)).scalar_one()
        assert inv.reserved == 3
        assert (inv.stock - inv.reserved) == 7


def test_batch_expiry_handles_multiple_orders_cleanly():
    """
    Multiple expired orders in AWAITING_PAYMENT are all processed in batch using
    FOR UPDATE SKIP LOCKED and release their stock correctly.
    """
    sku_a = "TTL-BATCH-A"
    sku_b = "TTL-BATCH-B"
    seed_inventory(sku=sku_a, stock=10, reserved=0)
    seed_inventory(sku=sku_b, stock=10, reserved=0)

    base_time = datetime(2026, 9, 23, 10, 0, 0, tzinfo=UTC)

    with TestingSessionLocal() as session:
        reserve_stock(
            db=session,
            sku=sku_a,
            qty=4,
            order_id="ORD-BATCH-1",
            shop_id="default",
            now_fn=lambda: base_time,
            ttl_seconds=300,
        )
        order_1 = Order(
            id="ORD-BATCH-1",
            shop_id="default",
            line_user_id="user_1",
            status=OrderStatus.AWAITING_PAYMENT.value,
            total=Decimal("1200.00"),
            currency="THB",
            ttl_expires_at=base_time + timedelta(seconds=300),
        )
        reserve_stock(
            db=session,
            sku=sku_b,
            qty=5,
            order_id="ORD-BATCH-2",
            shop_id="default",
            now_fn=lambda: base_time,
            ttl_seconds=400,
        )
        order_2 = Order(
            id="ORD-BATCH-2",
            shop_id="default",
            line_user_id="user_2",
            status=OrderStatus.AWAITING_PAYMENT.value,
            total=Decimal("1500.00"),
            currency="THB",
            ttl_expires_at=base_time + timedelta(seconds=400),
        )
        session.add_all([order_1, order_2])
        session.commit()

    # Fast forward to T+500s where both are expired
    t_after = base_time + timedelta(seconds=500)
    with TestingSessionLocal() as session:
        expired_ids = expire_stale_reservations(db=session, now_fn=lambda: t_after)
        assert "ORD-BATCH-1" in expired_ids
        assert "ORD-BATCH-2" in expired_ids

        # Both stock counters returned to 0 reserved
        inv_a = session.execute(select(Inventory).where(Inventory.sku == sku_a)).scalar_one()
        inv_b = session.execute(select(Inventory).where(Inventory.sku == sku_b)).scalar_one()
        assert inv_a.reserved == 0
        assert inv_b.reserved == 0
