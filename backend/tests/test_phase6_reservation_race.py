import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from sqlalchemy import select

from app.models.inventory import Inventory
from app.models.order import Order, OrderItem, OrderStatus
from app.services.reservation_service import (
    InsufficientStockError,
    reserve_order_stock,
    reserve_stock,
)
from tests.conftest import TestingSessionLocal


def seed_inventory_item(
    sku: str,
    stock: int = 1,
    reserved: int = 0,
    price: Decimal = Decimal("500.00"),
    shop_id: str | None = "default",
) -> None:
    """Helper to seed an inventory item directly in PostgreSQL."""
    with TestingSessionLocal() as db:
        item = Inventory(
            sku=sku,
            shop_id=shop_id,
            name=f"Test Product {sku}",
            category="Apparel",
            price=price,
            stock=stock,
            reserved=reserved,
            active=True,
            version=1,
        )
        db.add(item)
        db.commit()


def test_concurrent_threads_reserve_last_unit_exactly_one_succeeds():
    """
    CRITICAL CONCURRENCY REQUIREMENT (v1_buildable_spec.md §12, §20, TEST_PLAN.md):
    Two concurrent threads both attempting to reserve the last unit of stock:
    - Real PostgreSQL (app_test database, NOT SQLite, NOT mocked DB).
    - Real concurrent DB sessions in separate threads via ThreadPoolExecutor.
    - Synchronized via threading.Barrier to ensure real simultaneous execution.
    - Exactly one thread succeeds.
    - The other thread gets a clean InsufficientStockError.
    - Final DB state: stock = 1, reserved = 1, available = 0.
    """
    sku = "RACE-SKU-001"
    seed_inventory_item(sku=sku, stock=1, reserved=0)

    barrier = threading.Barrier(2)
    results: list[dict[str, object]] = []
    lock = threading.Lock()

    def attempt_reservation(thread_idx: int) -> None:
        order_id = f"ORD-RACE-{thread_idx}"
        # Wait for both threads to be ready to execute simultaneously
        barrier.wait()
        with TestingSessionLocal() as session:
            try:
                reservation = reserve_stock(
                    db=session,
                    sku=sku,
                    qty=1,
                    order_id=order_id,
                    shop_id="default",
                )
                with lock:
                    results.append(
                        {"thread": thread_idx, "success": True, "reservation": reservation}
                    )
            except InsufficientStockError as exc:
                with lock:
                    results.append({"thread": thread_idx, "success": False, "error": exc})

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_reservation, 1)
        f2 = executor.submit(attempt_reservation, 2)
        f1.result()
        f2.result()

    # 1. Assert exactly 2 results collected
    assert len(results) == 2

    successes = [r for r in results if r["success"] is True]
    failures = [r for r in results if r["success"] is False]

    # 2. Exactly one thread succeeds
    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {results}"

    # 3. Exactly one thread gets clean InsufficientStockError
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}: {results}"
    assert isinstance(failures[0]["error"], InsufficientStockError)

    # 4. Verify authoritative database state in PostgreSQL
    with TestingSessionLocal() as session:
        inv = session.execute(select(Inventory).where(Inventory.sku == sku)).scalar_one()
        assert inv.stock == 1
        assert inv.reserved == 1
        assert (inv.stock - inv.reserved) == 0


def test_concurrent_order_reservation_competing_for_limited_stock():
    """
    Two concurrent orders competing for stock of 3 units when order requires 2 units.
    Order 1 requests 2 units, Order 2 requests 2 units.
    Exactly one order succeeds, the other fails with InsufficientStockError.
    """
    sku = "RACE-SKU-002"
    seed_inventory_item(sku=sku, stock=3, reserved=0)

    # Seed two orders with line items in PostgreSQL
    with TestingSessionLocal() as session:
        order_a = Order(
            id="ORD-MULTI-A",
            shop_id="default",
            line_user_id="user_a",
            status=OrderStatus.ADDRESS_CONFIRMED.value,
            total=Decimal("1000.00"),
            currency="THB",
        )
        item_a = OrderItem(
            order_id=order_a.id,
            shop_id="default",
            sku=sku,
            name="Test Race Item",
            qty=2,
            unit_price=Decimal("500.00"),
            line_total=Decimal("1000.00"),
        )
        order_b = Order(
            id="ORD-MULTI-B",
            shop_id="default",
            line_user_id="user_b",
            status=OrderStatus.ADDRESS_CONFIRMED.value,
            total=Decimal("1000.00"),
            currency="THB",
        )
        item_b = OrderItem(
            order_id=order_b.id,
            shop_id="default",
            sku=sku,
            name="Test Race Item",
            qty=2,
            unit_price=Decimal("500.00"),
            line_total=Decimal("1000.00"),
        )
        session.add_all([order_a, item_a, order_b, item_b])
        session.commit()

    barrier = threading.Barrier(2)
    results: list[dict[str, object]] = []
    lock = threading.Lock()

    def attempt_order_reserve(order_id: str) -> None:
        barrier.wait()
        with TestingSessionLocal() as session:
            try:
                reserved_order = reserve_order_stock(
                    db=session,
                    order_id=order_id,
                    shop_id="default",
                )
                with lock:
                    results.append({"order_id": order_id, "success": True, "order": reserved_order})
            except InsufficientStockError as exc:
                with lock:
                    results.append({"order_id": order_id, "success": False, "error": exc})

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_order_reserve, "ORD-MULTI-A")
        f2 = executor.submit(attempt_order_reserve, "ORD-MULTI-B")
        f1.result()
        f2.result()

    successes = [r for r in results if r["success"] is True]
    failures = [r for r in results if r["success"] is False]

    assert len(successes) == 1
    assert len(failures) == 1

    winning_order_id = str(successes[0]["order_id"])
    losing_order_id = str(failures[0]["order_id"])

    with TestingSessionLocal() as session:
        inv = session.execute(select(Inventory).where(Inventory.sku == sku)).scalar_one()
        assert inv.stock == 3
        assert inv.reserved == 2  # exactly 2 reserved
        assert (inv.stock - inv.reserved) == 1

        winner = session.execute(select(Order).where(Order.id == winning_order_id)).scalar_one()
        loser = session.execute(select(Order).where(Order.id == losing_order_id)).scalar_one()

        assert winner.status == OrderStatus.AWAITING_PAYMENT.value
        assert winner.ttl_expires_at is not None
        assert loser.status == OrderStatus.ADDRESS_CONFIRMED.value
