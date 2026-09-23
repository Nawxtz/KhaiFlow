from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.payment import ConsumedPaymentClaim, Reservation


class EscalationError(Exception):
    """Base exception for escalation and manual review errors."""

    pass


class OrderNotFoundError(EscalationError):
    """Raised when the specified order ID is not found."""

    pass


class InvalidApprovalStateError(EscalationError):
    """Raised when an order cannot be approved or rejected due to invalid state."""

    pass


def get_current_time(now_fn: Callable[[], datetime] | None = None) -> datetime:
    """Return current UTC timestamp using injected now_fn or default system time."""
    if now_fn is not None:
        return now_fn()
    return datetime.now(UTC)


def check_escalation_tier(elapsed_minutes: float) -> str:
    """
    Determine escalation tier based on elapsed review minutes per reference_settings.md:
    - esc_reminder_minutes = 10
    - esc_urgent_backup_minutes = 15
    - esc_auto_action_minutes = 30
    - esc_hard_ceiling_hours = 24 (1440 min)
    """
    if elapsed_minutes >= 1440:
        return "HARD_CEILING"
    if elapsed_minutes >= 30:
        return "AUTO_ACTION"
    if elapsed_minutes >= 15:
        return "URGENT_BACKUP"
    if elapsed_minutes >= 10:
        return "REMINDER"
    return "NORMAL"


def escalate_for_manual_review(
    order_id: str,
    db: Session,
    shop_id: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> Order:
    """
    Escalate order for Option B seller manual approval per v1_buildable_spec.md §13.
    Transitions order to AWAITING_SELLER_APPROVAL.
    """
    stmt = select(Order).where(Order.id == order_id)
    if shop_id:
        stmt = stmt.where(Order.shop_id == shop_id)
    order = db.execute(stmt).scalars().first()

    if not order:
        raise OrderNotFoundError(f"Order '{order_id}' not found.")

    order.approval_state = "AWAITING_SELLER_APPROVAL"
    # Transition status: PAYMENT_VERIFYING or AWAITING_PAYMENT -> AWAITING_SELLER_APPROVAL
    # Note: Keep order in recognizable state machine state
    order.updated_at = get_current_time(now_fn)

    db.commit()
    db.refresh(order)
    return order


def approve_manual(
    order_id: str,
    reviewer_id: str,
    db: Session,
    shop_id: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> Order:
    """
    Option B seller manual approval.
    - Transitions order to PAYMENT_RECEIVED.
    - Flips associated consumed_payment_claims from PENDING to CONFIRMED.
    - Marks reservations CONFIRMED.
    - Clears order.ttl_expires_at.
    """
    stmt = select(Order).where(Order.id == order_id)
    if shop_id:
        stmt = stmt.where(Order.shop_id == shop_id)
    order = db.execute(stmt).scalars().first()

    if not order:
        raise OrderNotFoundError(f"Order '{order_id}' not found.")

    now_dt = get_current_time(now_fn)
    order.approval_state = "APPROVED"
    order.status = OrderStatus.PAYMENT_RECEIVED.value
    order.ttl_expires_at = None
    order.updated_at = now_dt

    # 1. Flip PENDING claims to CONFIRMED
    claims_stmt = select(ConsumedPaymentClaim).where(
        ConsumedPaymentClaim.order_id == order_id,
        ConsumedPaymentClaim.state == "PENDING",
    )
    pending_claims = list(db.execute(claims_stmt).scalars().all())
    for claim in pending_claims:
        claim.state = "CONFIRMED"

    # 2. Confirm reservations
    res_stmt = select(Reservation).where(
        Reservation.order_id == order_id,
        Reservation.state == "RESERVED",
    )
    for res in db.execute(res_stmt).scalars().all():
        res.state = "CONFIRMED"

    db.commit()
    db.refresh(order)
    return order


def reject_manual(
    order_id: str,
    reviewer_id: str,
    reason: str,
    db: Session,
    shop_id: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> Order:
    """
    Option B seller manual rejection.
    - Releases reservations and restores inventory available stock.
    - Releases PENDING payment claims (archives key to RELEASED:... to free reference).
    - Sets order.approval_state = 'REJECTED' and order.status = 'CANCELLED'.
    - Clears order.ttl_expires_at.
    """
    stmt = select(Order).where(Order.id == order_id)
    if shop_id:
        stmt = stmt.where(Order.shop_id == shop_id)
    order = db.execute(stmt).scalars().first()

    if not order:
        raise OrderNotFoundError(f"Order '{order_id}' not found.")

    now_dt = get_current_time(now_fn)

    # 1. Release active reservations and reverse held stock
    res_stmt = select(Reservation).where(
        Reservation.order_id == order_id,
        Reservation.state == "RESERVED",
    )
    active_reservations = list(db.execute(res_stmt).scalars().all())
    for res in active_reservations:
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

    # 2. Release PENDING claims so reference can be reused if appropriate
    claims_stmt = select(ConsumedPaymentClaim).where(
        ConsumedPaymentClaim.order_id == order_id,
        ConsumedPaymentClaim.state == "PENDING",
    )
    pending_claims = list(db.execute(claims_stmt).scalars().all())
    for claim in pending_claims:
        original_key = claim.claim_key
        claim.claim_key = f"RELEASED:{original_key}:{int(now_dt.timestamp())}"
        claim.state = "RELEASED"

    order.approval_state = "REJECTED"
    order.status = "CANCELLED"
    order.ttl_expires_at = None
    order.updated_at = now_dt

    db.commit()
    db.refresh(order)
    return order


def release_stale_claims(
    db: Session,
    shop_id: str | None = None,
    hard_ceiling_hours: int = 24,
    now_fn: Callable[[], datetime] | None = None,
) -> list[str]:
    """
    T+24h hard ceiling release job per v1_buildable_spec.md §13, §20.
    Queries consumed_payment_claims WHERE state = 'PENDING' AND consumed_at < :now - 24h.
    Uses FOR UPDATE SKIP LOCKED to prevent double-processing across workers.

    For each stale claim:
      - Sets state = 'RELEASED'.
      - Namespaces claim_key to 'RELEASED:{original_key}:{timestamp}' freeing the original
        key under the UNIQUE constraint for subsequent orders.
      - Releases any held reservations for the associated order.
    """
    now = get_current_time(now_fn)
    cutoff = now - timedelta(hours=hard_ceiling_hours)

    stmt = (
        select(ConsumedPaymentClaim)
        .where(
            ConsumedPaymentClaim.state == "PENDING",
            ConsumedPaymentClaim.consumed_at < cutoff,
        )
        .with_for_update(skip_locked=True)
    )
    if shop_id:
        stmt = stmt.where(ConsumedPaymentClaim.shop_id == shop_id)

    stale_claims = list(db.execute(stmt).scalars().all())
    released_keys: list[str] = []

    for claim in stale_claims:
        original_key = claim.claim_key
        archived_key = f"RELEASED:{original_key}:{int(now.timestamp())}"
        claim.claim_key = archived_key
        claim.state = "RELEASED"
        released_keys.append(original_key)

        # Release stock reservation if order is still held
        if claim.order_id:
            res_stmt = select(Reservation).where(
                Reservation.order_id == claim.order_id,
                Reservation.state == "RESERVED",
            )
            active_res = list(db.execute(res_stmt).scalars().all())
            for res in active_res:
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

            order_stmt = select(Order).where(Order.id == claim.order_id)
            order = db.execute(order_stmt).scalars().first()
            if order and order.status in {
                OrderStatus.AWAITING_PAYMENT.value,
                "AWAITING_SELLER_APPROVAL",
                "PAYMENT_VERIFYING",
            }:
                order.approval_state = "RELEASED_HARD_CEILING"
                order.status = "CANCELLED"
                order.ttl_expires_at = None

    db.commit()
    return released_keys
