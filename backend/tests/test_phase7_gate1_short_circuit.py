from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.payment import ConsumedPaymentClaim
from app.models.verification_log import VerificationLog
from app.services.verification_service import (
    build_test_slip_qr,
    verify_slip_local,
)


def seed_order(
    db: Session,
    order_id: str,
    total: Decimal = Decimal("450.00"),
    status: str = OrderStatus.AWAITING_PAYMENT.value,
    shop_id: str = "default",
) -> Order:
    """Helper to seed an order for verification testing."""
    order = Order(
        id=order_id,
        shop_id=shop_id,
        line_user_id="U_test_gate1",
        status=status,
        total=total,
        currency="THB",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def test_gate1_rejects_malformed_tlv_structure_before_any_db_write(
    db_session: Session, client: TestClient
):
    """
    CRITICAL HUMAN REVIEWER ITEM 2 (TEST_PLAN.md Phase 7, v1_buildable_spec.md §13):
    Malformed slip (bad TLV structure) — hard reject immediately;
    zero verification_logs rows written, zero consumed_payment_claims rows written.
    """
    order = seed_order(db_session, "ORD-TLV-BAD", total=Decimal("450.00"))

    # Malformed QR: Tag 54 specifies length 99 but payload is only 10 chars
    malformed_qr = "0002015499TOO_SHORT"

    # 1. Direct service verification check
    result = verify_slip_local(
        slip_data={"raw_qr": malformed_qr},
        expected_amount=order.total,
        order_id=order.id,
    )
    assert not result.passed
    assert "Malformed TLV" in result.reason or "invalid" in result.reason.lower()

    # 2. Endpoint call check
    response = client.post(
        "/api/verification/slip",
        json={
            "order_id": order.id,
            "slip_data": {"raw_qr": malformed_qr},
            "slip_hash": "hash_bad_tlv_123",
        },
    )
    assert response.status_code == 400
    resp_data = response.json()
    assert resp_data["passed"] is False

    # 3. Assert ZERO rows written to DB
    logs_count = db_session.execute(
        select(func.count(VerificationLog.id)).where(VerificationLog.order_id == order.id)
    ).scalar_one()
    claims_count = db_session.execute(
        select(func.count(ConsumedPaymentClaim.id)).where(ConsumedPaymentClaim.order_id == order.id)
    ).scalar_one()

    assert logs_count == 0, f"Expected 0 verification_logs rows, got {logs_count}"
    assert claims_count == 0, f"Expected 0 consumed_payment_claims rows, got {claims_count}"


def test_gate1_rejects_bad_crc_before_any_db_write(db_session: Session, client: TestClient):
    """
    CRITICAL HUMAN REVIEWER ITEM 2 (TEST_PLAN.md Phase 7, v1_buildable_spec.md §13):
    Malformed slip (bad CRC checksum) — hard reject immediately;
    zero verification_logs rows written, zero consumed_payment_claims rows written.
    """
    order = seed_order(db_session, "ORD-CRC-BAD", total=Decimal("500.00"))

    # Build QR with deliberately corrupted CRC (valid_crc=False appends 0000 instead of correct CRC)
    bad_crc_qr = build_test_slip_qr(
        amount=Decimal("500.00"),
        trans_ref="REF-CRC-FAIL",
        valid_crc=False,
    )

    # 1. Direct service check
    result = verify_slip_local(
        slip_data={"raw_qr": bad_crc_qr},
        expected_amount=order.total,
        order_id=order.id,
    )
    assert not result.passed
    assert "CRC" in result.reason

    # 2. Endpoint call check
    response = client.post(
        "/api/verification/slip",
        json={
            "order_id": order.id,
            "slip_data": {"raw_qr": bad_crc_qr},
            "slip_hash": "hash_bad_crc_456",
        },
    )
    assert response.status_code == 400
    assert response.json()["passed"] is False

    # 3. Assert ZERO rows written to DB
    logs_count = db_session.execute(
        select(func.count(VerificationLog.id)).where(VerificationLog.order_id == order.id)
    ).scalar_one()
    claims_count = db_session.execute(
        select(func.count(ConsumedPaymentClaim.id)).where(ConsumedPaymentClaim.order_id == order.id)
    ).scalar_one()

    assert logs_count == 0, f"Expected 0 verification_logs rows, got {logs_count}"
    assert claims_count == 0, f"Expected 0 consumed_payment_claims rows, got {claims_count}"


def test_gate1_rejects_tag54_amount_mismatch_before_any_db_write(
    db_session: Session, client: TestClient
):
    """
    Gate 1 check: Tag 54 amount mismatch beyond tolerance:
    Order total = 1000.00 THB, slip amount = 500.00 THB.
    Must hard reject with ZERO DB writes.
    """
    order = seed_order(db_session, "ORD-AMT-MISMATCH", total=Decimal("1000.00"))

    # Valid QR format and CRC, but amount is 500.00 instead of 1000.00
    mismatch_qr = build_test_slip_qr(
        amount=Decimal("500.00"),
        trans_ref="REF-AMT-DIFF",
        valid_crc=True,
    )

    result = verify_slip_local(
        slip_data={"raw_qr": mismatch_qr},
        expected_amount=order.total,
        order_id=order.id,
    )
    assert not result.passed
    assert "Tag 54" in result.reason or "tolerance" in result.reason

    response = client.post(
        "/api/verification/slip",
        json={
            "order_id": order.id,
            "slip_data": {"raw_qr": mismatch_qr},
        },
    )
    assert response.status_code == 400
    assert response.json()["passed"] is False

    logs_count = db_session.execute(
        select(func.count(VerificationLog.id)).where(VerificationLog.order_id == order.id)
    ).scalar_one()
    claims_count = db_session.execute(
        select(func.count(ConsumedPaymentClaim.id)).where(ConsumedPaymentClaim.order_id == order.id)
    ).scalar_one()

    assert logs_count == 0
    assert claims_count == 0


def test_gate1_rejects_zero_or_negative_amount_before_any_db_write(
    db_session: Session, client: TestClient
):
    """
    Gate 1 check: Non-positive amount rejected immediately without DB writes.
    """
    order = seed_order(db_session, "ORD-ZERO-AMT", total=Decimal("100.00"))

    result = verify_slip_local(
        slip_data={"amount": "0.00", "trans_ref": "REF-ZERO"},
        expected_amount=order.total,
        order_id=order.id,
    )
    assert not result.passed
    assert "positive non-zero" in result.reason

    response = client.post(
        "/api/verification/slip",
        json={
            "order_id": order.id,
            "slip_data": {"amount": "0.00", "trans_ref": "REF-ZERO"},
        },
    )
    assert response.status_code == 400

    logs_count = db_session.execute(
        select(func.count(VerificationLog.id)).where(VerificationLog.order_id == order.id)
    ).scalar_one()
    claims_count = db_session.execute(
        select(func.count(ConsumedPaymentClaim.id)).where(ConsumedPaymentClaim.order_id == order.id)
    ).scalar_one()

    assert logs_count == 0
    assert claims_count == 0


def test_gate1_passes_valid_slip_writes_log_and_creates_pending_claim(
    db_session: Session, client: TestClient
):
    """
    Valid slip passes Gate 1:
    - Writes exactly 1 row to verification_logs.
    - Writes exactly 1 row to consumed_payment_claims with state = 'PENDING'.
    - Advances order to AWAITING_SELLER_APPROVAL.
    """
    order = seed_order(db_session, "ORD-VALID-001", total=Decimal("450.00"))

    valid_qr = build_test_slip_qr(
        amount=Decimal("450.00"),
        trans_ref="VALID-REF-12345",
        valid_crc=True,
    )

    response = client.post(
        "/api/verification/slip",
        json={
            "order_id": order.id,
            "slip_data": {"raw_qr": valid_qr, "trans_ref": "VALID-REF-12345"},
            "slip_hash": "hash_valid_abc",
        },
    )
    assert response.status_code == 200
    resp_data = response.json()
    assert resp_data["passed"] is True
    assert resp_data["approval_state"] == "AWAITING_SELLER_APPROVAL"
    assert resp_data["claim_key"] == "ref:VALID-REF-12345"

    # Assert exactly 1 row written to verification_logs
    log = db_session.execute(
        select(VerificationLog).where(VerificationLog.order_id == order.id)
    ).scalar_one()
    assert log.result == "passed"
    assert log.slip_hash == "hash_valid_abc"
    assert log.risk_score == 0

    # Assert exactly 1 row written to consumed_payment_claims with state = 'PENDING'
    claim = db_session.execute(
        select(ConsumedPaymentClaim).where(ConsumedPaymentClaim.order_id == order.id)
    ).scalar_one()
    assert claim.claim_key == "ref:VALID-REF-12345"
    assert claim.state == "PENDING"
