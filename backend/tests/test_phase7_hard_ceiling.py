from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.order import Order, OrderStatus
from app.models.payment import ConsumedPaymentClaim, Reservation
from app.services.escalation_service import release_stale_claims
from app.services.reservation_service import reserve_stock
from app.services.verification_service import claim_payment


def seed_inventory(db: Session, sku: str, stock: int = 10, reserved: int = 0) -> None:
    item = Inventory(
        sku=sku,
        shop_id="default",
        name=f"Product {sku}",
        category="Apparel",
        price=Decimal("450.00"),
        stock=stock,
        reserved=reserved,
        active=True,
        version=1,
    )
    db.add(item)
    db.commit()


def seed_order_with_reservation(db: Session, order_id: str, sku: str, qty: int = 1) -> Order:
    order = Order(
        id=order_id,
        shop_id="default",
        line_user_id="U_test_user",
        status=OrderStatus.AWAITING_PAYMENT.value,
        total=Decimal("450.00"),
        currency="THB",
    )
    db.add(order)
    db.commit()
    reserve_stock(db, sku=sku, qty=qty, order_id=order_id, shop_id="default")
    return order


def test_hard_ceiling_releases_pending_claim_and_allows_reference_reuse(db_session: Session):
    """
    CRITICAL HUMAN REVIEWER ITEM 3 (TEST_PLAN.md Phase 7, v1_buildable_spec.md §13, §20):
    - Hard ceiling job updates consumed_payment_claims.state to RELEASED after T+24h.
    - Namespaces old claim_key to RELEASED:{key}:{ts}.
    - A new order can subsequently use the same reference claim_key.
    - Uses injected now_fn to fast-forward time to T+25h without time.sleep().
    """
    t0 = datetime(2026, 9, 23, 10, 0, 0, tzinfo=UTC)
    ref_key = "ref:SHARED-BANK-TRANS-888"
    order_1 = "ORD-ORIGINAL-001"
    order_2 = "ORD-COMPETING-002"
    order_3 = "ORD-NEW-REUSE-003"

    # 1. Order 1 claims the reference at T0 with state = 'PENDING'
    claim_1_id = claim_payment(
        db=db_session,
        claim_key=ref_key,
        order_id=order_1,
        shop_id="default",
        claim_type="ref",
        state="PENDING",
    )
    assert claim_1_id is not None

    # Manually backdate consumed_at to T0 for test isolation
    claim_1 = db_session.execute(
        select(ConsumedPaymentClaim).where(ConsumedPaymentClaim.id == claim_1_id)
    ).scalar_one()
    claim_1.consumed_at = t0
    db_session.commit()

    # 2. At T+1h, Order 2 tries to claim the same reference -> blocked as duplicate
    claim_2_id = claim_payment(
        db=db_session,
        claim_key=ref_key,
        order_id=order_2,
        shop_id="default",
        claim_type="ref",
        state="PENDING",
    )
    assert claim_2_id is None, "Order 2 must be blocked from claiming an active PENDING claim"

    t25 = t0 + timedelta(hours=25)

    def now_fn_future() -> datetime:
        return t25

    # Run the hard ceiling release job
    released_keys = release_stale_claims(
        db=db_session,
        shop_id="default",
        hard_ceiling_hours=24,
        now_fn=now_fn_future,
    )
    assert ref_key in released_keys

    # Verify the original claim is now marked RELEASED and namespaced
    db_session.refresh(claim_1)
    assert claim_1.state == "RELEASED"
    assert claim_1.claim_key.startswith(f"RELEASED:{ref_key}")

    # 4. Order 3 attempts to claim the same reference -> SUCCEEDS!
    claim_3_id = claim_payment(
        db=db_session,
        claim_key=ref_key,
        order_id=order_3,
        shop_id="default",
        claim_type="ref",
        state="PENDING",
    )
    assert claim_3_id is not None, "Order 3 must successfully claim the released reference"
    assert claim_3_id != claim_1_id

    claim_3 = db_session.execute(
        select(ConsumedPaymentClaim).where(ConsumedPaymentClaim.id == claim_3_id)
    ).scalar_one()
    assert claim_3.claim_key == ref_key
    assert claim_3.state == "PENDING"
    assert claim_3.order_id == order_3


def test_hard_ceiling_does_not_release_fresh_claims(db_session: Session):
    """Claims newer than T+24h must remain PENDING and not be released."""
    t0 = datetime(2026, 9, 23, 10, 0, 0, tzinfo=UTC)
    ref_key = "ref:FRESH-CLAIM-123"

    claim_id = claim_payment(
        db=db_session,
        claim_key=ref_key,
        order_id="ORD-FRESH-001",
        state="PENDING",
    )
    assert claim_id is not None

    claim = db_session.execute(
        select(ConsumedPaymentClaim).where(ConsumedPaymentClaim.id == claim_id)
    ).scalar_one()
    claim.consumed_at = t0
    db_session.commit()

    # Fast-forward only 12 hours (under 24h hard ceiling threshold)
    t12 = t0 + timedelta(hours=12)
    released = release_stale_claims(db_session, now_fn=lambda: t12)

    assert len(released) == 0
    db_session.refresh(claim)
    assert claim.state == "PENDING"
    assert claim.claim_key == ref_key


def test_hard_ceiling_releases_order_reservation_and_restores_stock(db_session: Session):
    """
    When hard ceiling releases a stuck order, any held inventory reservations
    must be restored to physical inventory stock.
    """
    sku = "HC-SKU-999"
    seed_inventory(db_session, sku=sku, stock=5, reserved=0)

    order = seed_order_with_reservation(db_session, "ORD-STUCK-RESERVE", sku=sku, qty=2)

    inv = db_session.execute(select(Inventory).where(Inventory.sku == sku)).scalar_one()
    assert inv.reserved == 2

    # Claim payment with PENDING
    ref_key = "ref:STUCK-RESERVE-KEY"
    claim_id = claim_payment(db_session, claim_key=ref_key, order_id=order.id, state="PENDING")
    assert claim_id is not None

    claim = db_session.execute(
        select(ConsumedPaymentClaim).where(ConsumedPaymentClaim.id == claim_id)
    ).scalar_one()
    t0 = datetime(2026, 9, 23, 10, 0, 0, tzinfo=UTC)
    claim.consumed_at = t0
    db_session.commit()

    # Advance time 25 hours
    t25 = t0 + timedelta(hours=25)
    release_stale_claims(db_session, now_fn=lambda: t25)

    # Verify inventory reservation was reversed
    db_session.refresh(inv)
    assert inv.reserved == 0

    # Verify reservation state
    res = db_session.execute(
        select(Reservation).where(Reservation.order_id == order.id)
    ).scalar_one()
    assert res.state == "RELEASED"

    # Verify order state
    db_session.refresh(order)
    assert order.approval_state == "RELEASED_HARD_CEILING"
    assert order.status == "CANCELLED"
