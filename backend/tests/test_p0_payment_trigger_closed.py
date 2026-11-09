from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus


def test_payment_cannot_be_marked_paid_over_http(client: TestClient, db_session: Session):
    order = Order(
        id="ORD-P0-TRIGGER",
        shop_id="default",
        line_user_id="U_p0_buyer",
        status=OrderStatus.AWAITING_PAYMENT.value,
        total=Decimal("100.00"),
        currency="THB",
    )
    db_session.add(order)
    db_session.commit()

    response = client.post(
        "/api/payment/trigger",
        json={"claim_key": "ref:x", "order_id": order.id, "shop_id": "default", "channel": "web"},
    )

    assert response.status_code == 404
    db_session.refresh(order)
    assert order.status == OrderStatus.AWAITING_PAYMENT.value
