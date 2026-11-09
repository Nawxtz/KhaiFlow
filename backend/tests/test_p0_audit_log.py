from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.auth import User
from app.models.order import Order, OrderStatus


def _seed_order(db: Session, order_id: str) -> None:
    db.add(
        Order(
            id=order_id,
            shop_id="default",
            line_user_id="U_private_buyer",
            status=OrderStatus.AWAITING_PAYMENT.value,
            total=Decimal("100.00"),
            currency="THB",
            approval_state="AWAITING_SELLER_APPROVAL",
        )
    )
    db.commit()


def _audit_rows(db: Session) -> list[AuditLog]:
    db.expire_all()
    return list(db.execute(select(AuditLog)).scalars().all())


def test_approval_records_who_when_old_and_new(client: TestClient, db_session: Session):
    _seed_order(db_session, "ORD-AUDIT-1")

    assert client.post("/api/verification/approve/ORD-AUDIT-1", json={}).status_code == 200

    rows = _audit_rows(db_session)
    assert len(rows) == 1
    owner = db_session.execute(select(User).where(User.username == "test_owner")).scalars().one()
    assert rows[0].actor_user_id == owner.id
    assert rows[0].action == "payment.approve"
    assert rows[0].entity == "order"
    assert rows[0].entity_id == "ORD-AUDIT-1"
    assert rows[0].shop_id == "default"
    assert rows[0].created_at is not None
    assert rows[0].old_value == {
        "status": "AWAITING_PAYMENT",
        "approval_state": "AWAITING_SELLER_APPROVAL",
    }
    assert rows[0].new_value == {"status": "PAYMENT_RECEIVED", "approval_state": "APPROVED"}


def test_rejection_records_reason_and_change(client: TestClient, db_session: Session):
    _seed_order(db_session, "ORD-AUDIT-2")

    response = client.post("/api/verification/reject/ORD-AUDIT-2", json={"reason": "bad slip"})

    assert response.status_code == 200
    rows = _audit_rows(db_session)
    assert rows[0].action == "payment.reject"
    assert rows[0].new_value == {
        "status": "CANCELLED",
        "approval_state": "REJECTED",
        "reason": "bad slip",
    }


def test_refused_action_writes_no_audit_row(client: TestClient, db_session: Session):
    assert client.post("/api/verification/approve/ORD-NOT-THERE", json={}).status_code == 404

    assert _audit_rows(db_session) == []


def test_audit_row_has_no_buyer_identity(client: TestClient, db_session: Session):
    _seed_order(db_session, "ORD-AUDIT-3")

    client.post("/api/verification/approve/ORD-AUDIT-3", json={})

    row = _audit_rows(db_session)[0]
    assert "U_private_buyer" not in str((row.old_value, row.new_value, row.entity_id))
