from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.order import Order, OrderStatus
from app.models.payment import Reservation


class ReservationError(Exception):
    """Base exception for reservation errors."""

    pass


class InsufficientStockError(ReservationError):
    """Raised when atomic inventory reservation fails due to insufficient available stock."""

    def __init__(self, sku: str, requested_qty: int, shop_id: str | None = None) -> None:
        super().__init__(
            f"Insufficient available stock for SKU '{sku}' (requested: {requested_qty}, shop_id: {shop_id})."
        )
        self.sku = sku
        self.requested_qty = requested_qty
        self.shop_id = shop_id


class OrderNotFoundError(ReservationError):
    """Raised when the specified order ID is not found."""

    def __init__(self, order_id: str) -> None:
        super().__init__(f"Order '{order_id}' not found.")
        self.order_id = order_id


class InvalidOrderStateError(ReservationError):
    """Raised when order is in an invalid state for reservation."""

    def __init__(self, order_id: str, current_status: str) -> None:
        super().__init__(
            f"Cannot reserve stock for order '{order_id}' in status '{current_status}'."
        )
        self.order_id = order_id
        self.current_status = current_status


def get_current_time(now_fn: Callable[[], datetime] | None = None) -> datetime:
    """Return current UTC timestamp using injected now_fn or default system time."""
    if now_fn is not None:
        return now_fn()
    return datetime.now(UTC)


def reserve_stock(
    db: Session,
    sku: str,
    qty: int,
    order_id: str,
    shop_id: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
    ttl_seconds: int | None = None,
) -> Reservation:
    """
    Atomically reserve stock for a single SKU using a single SQL UPDATE.
    No SELECT-then-UPDATE and no .with_for_update() on SELECT.

    The atomic conditional UPDATE checks (stock - reserved) >= :qty and active = TRUE.
    Evaluates rowcount == 1:
      - 1: Reservation succeeded.
      - 0: Reservation failed (concurrent race lost or out of stock).
    """
    if qty <= 0:
        raise ValueError("Quantity to reserve must be greater than zero.")

    ttl = ttl_seconds if ttl_seconds is not None else settings.RESERVATION_TTL_SECONDS
    now_dt = get_current_time(now_fn)
    expires_at = now_dt + timedelta(seconds=ttl)

    # Single atomic SQL statement per CONCURRENCY.md and spec §12
    if shop_id is not None:
        update_stmt = text(
            """
            UPDATE inventory
            SET reserved = reserved + :qty, version = version + 1
            WHERE sku = :sku
              AND shop_id = :shop_id
              AND (stock - reserved) >= :qty
              AND active = TRUE
            """
        )
        params: dict[str, Any] = {"sku": sku, "qty": qty, "shop_id": shop_id}
    else:
        update_stmt = text(
            """
            UPDATE inventory
            SET reserved = reserved + :qty, version = version + 1
            WHERE sku = :sku
              AND (stock - reserved) >= :qty
              AND active = TRUE
            """
        )
        params = {"sku": sku, "qty": qty}

    result = cast(CursorResult[Any], db.execute(update_stmt, params))

    if result.rowcount != 1:
        # Atomic reservation failed (either stock exhausted or lost concurrent race)
        db.rollback()
        raise InsufficientStockError(sku=sku, requested_qty=qty, shop_id=shop_id)

    reservation = Reservation(
        order_id=order_id,
        shop_id=shop_id,
        sku=sku,
        qty=qty,
        state="RESERVED",
        expires_at=expires_at,
        created_at=now_dt,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


def reserve_order_stock(
    db: Session,
    order_id: str,
    shop_id: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
    ttl_seconds: int | None = None,
) -> Order:
    """
    Atomically reserve stock for all line items in an order.
    Executes within a single transaction. If any line item fails atomic reservation,
    all previous items are rolled back and InsufficientStockError is raised.

    On success, updates Order status to AWAITING_PAYMENT and sets ttl_expires_at.
    """
    # 1. Fetch order
    stmt = select(Order).where(Order.id == order_id)
    if shop_id:
        stmt = stmt.where(Order.shop_id == shop_id)
    order = db.execute(stmt).scalars().first()

    if not order:
        raise OrderNotFoundError(order_id)

    # Verify allowable pre-reservation states
    allowable_statuses = {
        OrderStatus.ORDER_CONFIRMED.value,
        OrderStatus.ADDRESS_CONFIRMED.value,
        OrderStatus.ORDER_DRAFT.value,
    }
    if order.status not in allowable_statuses:
        raise InvalidOrderStateError(order_id, order.status)

    if not order.items:
        raise ReservationError(f"Order '{order_id}' has no line items to reserve.")

    ttl = ttl_seconds if ttl_seconds is not None else settings.RESERVATION_TTL_SECONDS
    now_dt = get_current_time(now_fn)
    expires_at = now_dt + timedelta(seconds=ttl)

    # 2. Atomically reserve each item using single atomic conditional UPDATE
    for item in order.items:
        if order.shop_id is not None:
            update_stmt = text(
                """
                UPDATE inventory
                SET reserved = reserved + :qty, version = version + 1
                WHERE sku = :sku
                  AND shop_id = :shop_id
                  AND (stock - reserved) >= :qty
                  AND active = TRUE
                """
            )
            params: dict[str, Any] = {"sku": item.sku, "qty": item.qty, "shop_id": order.shop_id}
        else:
            update_stmt = text(
                """
                UPDATE inventory
                SET reserved = reserved + :qty, version = version + 1
                WHERE sku = :sku
                  AND (stock - reserved) >= :qty
                  AND active = TRUE
                """
            )
            params = {"sku": item.sku, "qty": item.qty}

        result = cast(CursorResult[Any], db.execute(update_stmt, params))

        if result.rowcount != 1:
            # Atomic update failed: insufficient stock or lost race
            db.rollback()
            raise InsufficientStockError(
                sku=item.sku,
                requested_qty=item.qty,
                shop_id=order.shop_id,
            )

        # Record reservation
        reservation = Reservation(
            order_id=order.id,
            shop_id=order.shop_id,
            sku=item.sku,
            qty=item.qty,
            state="RESERVED",
            expires_at=expires_at,
            created_at=now_dt,
        )
        db.add(reservation)

    # 3. Transition order status: ADDRESS_CONFIRMED -> AWAITING_PAYMENT
    order.status = OrderStatus.AWAITING_PAYMENT.value
    order.ttl_expires_at = expires_at

    db.commit()
    db.refresh(order)
    return order


def release_stock(
    db: Session,
    sku: str,
    qty: int,
    order_id: str | None = None,
    shop_id: str | None = None,
) -> bool:
    """
    Atomically release reserved stock:
    UPDATE inventory SET reserved = reserved - :qty, version = version + 1
    WHERE sku = :sku AND reserved >= :qty
    """
    if qty <= 0:
        return True

    reverse_stmt = text(
        """
        UPDATE inventory
        SET reserved = reserved - :qty, version = version + 1
        WHERE sku = :sku
          AND reserved >= :qty
        """
    )
    result = cast(CursorResult[Any], db.execute(reverse_stmt, {"sku": sku, "qty": qty}))

    if order_id:
        # Mark reservation records as RELEASED
        reservations_stmt = select(Reservation).where(
            Reservation.order_id == order_id,
            Reservation.sku == sku,
            Reservation.state == "RESERVED",
        )
        for res in db.execute(reservations_stmt).scalars().all():
            res.state = "RELEASED"

    db.commit()
    return result.rowcount == 1


def expire_stale_reservations(
    db: Session,
    now_fn: Callable[[], datetime] | None = None,
) -> list[str]:
    """
    Background TTL expiry job per v1_buildable_spec.md §12, §20.
    Queries orders WHERE status = 'AWAITING_PAYMENT' AND ttl_expires_at < now().
    Uses SELECT ... FOR UPDATE SKIP LOCKED to prevent double-processing across workers.

    For each expired order:
      1. Atomically reverses reserved quantity (UPDATE inventory SET reserved = reserved - qty).
      2. Updates reservation records to state = 'RELEASED'.
      3. Sets order status to RESERVATION_EXPIRED and clears ttl_expires_at.
    """
    now_dt = get_current_time(now_fn)

    # Batch query with FOR UPDATE SKIP LOCKED for multi-worker safety
    expired_orders_stmt = (
        select(Order)
        .where(
            Order.status == OrderStatus.AWAITING_PAYMENT.value,
            Order.ttl_expires_at.is_not(None),
            Order.ttl_expires_at < now_dt,
        )
        .with_for_update(skip_locked=True)
    )

    expired_orders = list(db.execute(expired_orders_stmt).scalars().all())
    expired_order_ids: list[str] = []

    for order in expired_orders:
        # Fetch active reservations for this order
        res_stmt = select(Reservation).where(
            Reservation.order_id == order.id,
            Reservation.state == "RESERVED",
        )
        active_reservations = list(db.execute(res_stmt).scalars().all())

        for res in active_reservations:
            # Atomic reverse update per spec §12
            reverse_stmt = text(
                """
                UPDATE inventory
                SET reserved = reserved - :qty, version = version + 1
                WHERE sku = :sku
                  AND reserved >= :qty
                """
            )
            db.execute(reverse_stmt, {"sku": res.sku, "qty": res.qty})
            res.state = "RELEASED"

        # Advance order state: AWAITING_PAYMENT -> RESERVATION_EXPIRED
        order.status = OrderStatus.RESERVATION_EXPIRED.value
        order.ttl_expires_at = None
        expired_order_ids.append(order.id)

    db.commit()
    return expired_order_ids
