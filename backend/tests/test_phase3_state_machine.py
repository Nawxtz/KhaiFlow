from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.order import OrderStatus
from app.services.order_service import (
    EmptyCartError,
    OutOfStockError,
    add_item_to_draft,
    confirm_draft_order,
    get_active_draft_order,
    get_or_create_draft_order,
)


@pytest.fixture
def sample_items(db_session: Session) -> list[Inventory]:
    items = [
        Inventory(
            sku="SM-SKU-01",
            name="Silk Handkerchief",
            category="Accessories",
            price=Decimal("120.00"),
            stock=5,
            reserved=0,
            active=True,
        ),
        Inventory(
            sku="SM-SKU-02",
            name="Cotton Cap",
            category="Apparel",
            price=Decimal("250.00"),
            stock=1,
            reserved=0,
            active=True,
        ),
    ]
    db_session.add_all(items)
    db_session.commit()
    return items


def test_state_machine_transition_browsing_to_draft_to_confirmed(
    db_session: Session, sample_items: list[Inventory]
):
    """
    State machine test (§8):
    Verifies BROWSING -> ORDER_DRAFT -> ORDER_CONFIRMED transitions.
    """
    user_id = "U_sm_user_01"

    # Initially no draft exists
    initial_draft = get_active_draft_order(db_session, line_user_id=user_id)
    assert initial_draft is None

    # Adding an item transitions to ORDER_DRAFT
    item, order = add_item_to_draft(
        db_session,
        line_user_id=user_id,
        sku="SM-SKU-01",
        qty=2,
    )
    assert order.status == OrderStatus.ORDER_DRAFT.value
    assert order.total == Decimal("240.00")
    assert len(order.items) == 1

    # Confirming the draft transitions to ORDER_CONFIRMED
    confirmed_order = confirm_draft_order(db_session, line_user_id=user_id)
    assert confirmed_order.id == order.id
    assert confirmed_order.status == OrderStatus.ORDER_CONFIRMED.value
    assert confirmed_order.total == Decimal("240.00")

    # After confirmation, no active draft exists
    subsequent_draft = get_active_draft_order(db_session, line_user_id=user_id)
    assert subsequent_draft is None


def test_state_machine_rejects_empty_cart(db_session: Session):
    """State machine prevents confirming an empty cart."""
    user_id = "U_sm_empty_user"
    get_or_create_draft_order(db_session, line_user_id=user_id)

    with pytest.raises(EmptyCartError):
        confirm_draft_order(db_session, line_user_id=user_id)


def test_state_machine_rejects_out_of_stock_addition(
    db_session: Session, sample_items: list[Inventory]
):
    """State machine prevents adding items exceeding available stock."""
    user_id = "U_sm_stock_user"

    with pytest.raises(OutOfStockError):
        add_item_to_draft(
            db_session,
            line_user_id=user_id,
            sku="SM-SKU-02",
            qty=3,  # stock is 1
        )


def test_state_machine_accumulates_same_sku(db_session: Session, sample_items: list[Inventory]):
    """Adding same SKU increments qty instead of duplicate line items."""
    user_id = "U_sm_accum_user"

    add_item_to_draft(db_session, line_user_id=user_id, sku="SM-SKU-01", qty=1)
    add_item_to_draft(db_session, line_user_id=user_id, sku="SM-SKU-01", qty=2)

    order = get_active_draft_order(db_session, line_user_id=user_id)
    assert order is not None
    assert len(order.items) == 1
    assert order.items[0].qty == 3
    assert order.total == Decimal("360.00")
