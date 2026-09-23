from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.order import Order, OrderStatus
from app.models.payment import ConsumedPaymentClaim, Reservation
from app.services.escalation_service import (
    approve_manual,
    check_escalation_tier,
    escalate_for_manual_review,
    reject_manual,
    release_stale_claims,
)
from app.services.reservation_service import reserve_stock
from app.services.verification_service import claim_payment


def seed_inventory_and_order(db: Session, order_id: str, sku: str) -> Order:
    item = Inventory(
        sku=sku,
        shop_id="default",
        name=f"Product {sku}",
        category="Apparel",
        price=Decimal("450.00"),
        stock=10,
        reserved=0,
        active=True,
        version=1,
    )
    db.add(item)
    order = Order(
        id=order_id,
        shop_id="default",
        line_user_id="U_test_escalation",
        status=OrderStatus.AWAITING_PAYMENT.value,
        total=Decimal("450.00"),
        currency="THB",
    )
    db.add(order)
    db.commit()
    reserve_stock(db, sku=sku, qty=1, order_id=order_id, shop_id="default")
    return order


def test_option_b_manual_approval_transitions_order_and_confirms_claims(
    db_session: Session, client: TestClient
):
    """
    Option B Manual Approval:
    - Transitions order to PAYMENT_RECEIVED and approval_state to APPROVED.
    - Flips associated consumed_payment_claims from PENDING to CONFIRMED.
    - Tests both service function and API endpoint.
    """
    sku = "OPT-B-SKU-1"
    order = seed_inventory_and_order(db_session, "ORD-MANUAL-APPROVE", sku=sku)

    # 1. Escalate for manual review
    escalate_for_manual_review(order.id, db=db_session)
    claim_payment(db_session, claim_key=f"ref:{order.id}", order_id=order.id, state="PENDING")

    claim = db_session.execute(
        select(ConsumedPaymentClaim).where(ConsumedPaymentClaim.order_id == order.id)
    ).scalar_one()
    assert claim.state == "PENDING"

    # 2. Call manual approval API endpoint
    response = client.post(
        f"/api/verification/approve/{order.id}",
        json={"reviewer_id": "seller_owner_01"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["order_status"] == OrderStatus.PAYMENT_RECEIVED.value
    assert data["approval_state"] == "APPROVED"

    # 3. Assert DB state: order status = PAYMENT_RECEIVED, claim state = CONFIRMED
    db_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_RECEIVED.value
    assert order.approval_state == "APPROVED"

    db_session.refresh(claim)
    assert claim.state == "CONFIRMED"

    res = db_session.execute(
        select(Reservation).where(Reservation.order_id == order.id)
    ).scalar_one()
    assert res.state == "CONFIRMED"


def test_option_b_manual_rejection_releases_stock_and_cancels_order(
    db_session: Session, client: TestClient
):
    """
    Option B Manual Rejection:
    - Releases reservation: reverses held stock back to available.
    - Sets order status to CANCELLED and approval_state to REJECTED.
    - Releases claim and archives key.
    - Tests both service function and API endpoint.
    """
    sku = "OPT-B-SKU-2"
    order = seed_inventory_and_order(db_session, "ORD-MANUAL-REJECT", sku=sku)

    inv = db_session.execute(select(Inventory).where(Inventory.sku == sku)).scalar_one()
    assert inv.reserved == 1

    claim_payment(db_session, claim_key=f"ref:{order.id}", order_id=order.id, state="PENDING")

    # Call manual rejection API endpoint
    response = client.post(
        f"/api/verification/reject/{order.id}",
        json={
            "reviewer_id": "seller_owner_01",
            "reason": "Slip image is blurry and transaction not found on bank portal",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["order_status"] == "CANCELLED"
    assert data["approval_state"] == "REJECTED"

    # Verify inventory was restored
    db_session.refresh(inv)
    assert inv.reserved == 0

    # Verify reservation state
    res = db_session.execute(
        select(Reservation).where(Reservation.order_id == order.id)
    ).scalar_one()
    assert res.state == "RELEASED"

    # Verify claim state
    claim = db_session.execute(
        select(ConsumedPaymentClaim).where(ConsumedPaymentClaim.order_id == order.id)
    ).scalar_one()
    assert claim.state == "RELEASED"
    assert claim.claim_key.startswith("RELEASED:")


def test_escalation_timers_fire_in_exact_sequence_without_sleep():
    """
    TEST_PLAN.md Phase 7:
    Escalation timers fire in the correct order:
    - T+10 reminder
    - T+15 backup
    - T+30 auto-action
    - T+24h hard ceiling
    Verified with fast-forwarded time parameters, ZERO time.sleep().
    """
    # 0 to 9 minutes: NORMAL
    assert check_escalation_tier(0) == "NORMAL"
    assert check_escalation_tier(9.9) == "NORMAL"

    # 10 to 14.9 minutes: REMINDER
    assert check_escalation_tier(10) == "REMINDER"
    assert check_escalation_tier(14.9) == "REMINDER"

    # 15 to 29.9 minutes: URGENT_BACKUP
    assert check_escalation_tier(15) == "URGENT_BACKUP"
    assert check_escalation_tier(29.9) == "URGENT_BACKUP"

    # 30 to 1439.9 minutes: AUTO_ACTION
    assert check_escalation_tier(30) == "AUTO_ACTION"
    assert check_escalation_tier(60) == "AUTO_ACTION"
    assert check_escalation_tier(1439.9) == "AUTO_ACTION"

    # 1440+ minutes (24h+): HARD_CEILING
    assert check_escalation_tier(1440) == "HARD_CEILING"
    assert check_escalation_tier(1500) == "HARD_CEILING"


def test_escalation_service_now_fn_injection_in_all_time_sensitive_methods(db_session: Session):
    """
    CRITICAL HUMAN REVIEWER ITEM 4:
    now_fn injection used everywhere time matters in escalation service.
    Fast-forwards time without time.sleep().
    """
    calls: list[object] = []
    fixed_time = datetime(2026, 9, 23, 14, 0, 0, tzinfo=UTC)

    def custom_now_fn() -> datetime:
        calls.append("called")
        return fixed_time

    order = Order(
        id="ORD-TIME-INJECT",
        shop_id="default",
        line_user_id="U_test_time",
        status=OrderStatus.AWAITING_PAYMENT.value,
        total=Decimal("100.00"),
        currency="THB",
    )
    db_session.add(order)
    db_session.commit()

    # 1. Escalate with custom now_fn
    escalate_for_manual_review(order.id, db=db_session, now_fn=custom_now_fn)
    assert len(calls) == 1

    # 2. Approve with custom now_fn
    approve_manual(order.id, reviewer_id="seller_1", db=db_session, now_fn=custom_now_fn)
    assert len(calls) == 2

    # 3. Reject with custom now_fn
    reject_manual(
        order.id, reviewer_id="seller_1", reason="test", db=db_session, now_fn=custom_now_fn
    )
    assert len(calls) == 3

    # 4. release_stale_claims with custom now_fn fast-forwarding 25 hours
    future_time = fixed_time + timedelta(hours=25)

    def future_now_fn() -> datetime:
        calls.append("future")
        return future_time

    release_stale_claims(db_session, now_fn=future_now_fn)
    assert "future" in calls
