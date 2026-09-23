import base64
import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.webhook import clear_processed_events, get_line_client
from app.core.line_client import LineClient
from app.main import app
from app.models.inventory import Inventory
from app.models.order import Order, OrderStatus
from app.models.user_prefs import UserPrefs
from app.services.i18n import get_text
from app.services.intent_router import clear_all_user_selections

TEST_SECRET = "test_channel_secret_key_12345"


def generate_line_signature(body: bytes, secret: str = TEST_SECRET) -> str:
    """Generate valid HMAC-SHA256 signature for LINE webhook payload."""
    computed_mac = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(computed_mac).decode("utf-8")


@pytest.fixture(autouse=True)
def reset_state():
    clear_processed_events()
    clear_all_user_selections()
    yield
    clear_processed_events()
    clear_all_user_selections()


@pytest.fixture
def mock_line_client():
    client = LineClient(
        channel_access_token="test_access_token",
        channel_secret=TEST_SECRET,
    )
    client.reply_message = MagicMock()
    return client


@pytest.fixture
def seed_catalog(db_session: Session):
    """Seed sample inventory products for ordering tests."""
    items = [
        Inventory(
            sku="SKU-SHIRT-01",
            name="Classic Cotton Shirt",
            category="Apparel",
            price=Decimal("490.00"),
            stock=15,
            reserved=0,
            active=True,
        ),
        Inventory(
            sku="SKU-SCARF-01",
            name="Thai Silk Scarf",
            category="Accessories",
            price=Decimal("350.00"),
            stock=10,
            reserved=0,
            active=True,
        ),
        Inventory(
            sku="SKU-LOW-01",
            name="Handmade Ceramic Mug",
            category="Home",
            price=Decimal("220.00"),
            stock=2,
            reserved=0,
            active=True,
        ),
        Inventory(
            sku="SKU-OUT-01",
            name="Vintage Wooden Plate",
            category="Home",
            price=Decimal("300.00"),
            stock=0,
            reserved=0,
            active=True,
        ),
    ]
    db_session.add_all(items)
    db_session.commit()
    return items


def _send_postback(
    client: TestClient, user_id: str, postback_data: str, reply_token: str = "tok_pb"
):
    payload = {
        "events": [
            {
                "webhookEventId": f"evt_{postback_data}_{reply_token}",
                "type": "postback",
                "source": {"type": "user", "userId": user_id},
                "replyToken": reply_token,
                "postback": {"data": postback_data},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"X-Line-Signature": generate_line_signature(body, TEST_SECRET)}
    return client.post("/line/webhook", content=body, headers=headers)


def _send_text(client: TestClient, user_id: str, text: str, reply_token: str = "tok_msg"):
    payload = {
        "events": [
            {
                "webhookEventId": f"evt_txt_{text}_{reply_token}",
                "type": "message",
                "source": {"type": "user", "userId": user_id},
                "replyToken": reply_token,
                "message": {"id": f"msg_{reply_token}", "type": "text", "text": text},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"X-Line-Signature": generate_line_signature(body, TEST_SECRET)}
    return client.post("/line/webhook", content=body, headers=headers)


def test_full_guided_flow_with_size_reaches_order_confirmed(
    client: TestClient,
    db_session: Session,
    mock_line_client: LineClient,
    seed_catalog: list[Inventory],
):
    """
    Acceptance criterion 1 (§20, TEST_PLAN.md):
    Full guided flow reaches ORDER_CONFIRMED.
    Sequence:
    a. Browse -> returns product Flex carousel.
    b. Select product (apparel) -> bot asks for size.
    c. Select size -> bot asks for quantity.
    d. Set quantity -> bot shows line subtotal and asks 'Add more or confirm?'.
    e. Confirm -> order status set to ORDER_CONFIRMED, bot replies with order summary.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_buyer_guided_01"

        # Step a: Buyer taps Browse
        res_browse = _send_postback(client, user_id, "action=browse", reply_token="tok_1")
        assert res_browse.status_code == 200
        assert mock_line_client.reply_message.call_count == 1
        carousel_reply = mock_line_client.reply_message.call_args[0][1][0]
        assert carousel_reply["type"] == "flex"
        assert carousel_reply["contents"]["type"] == "carousel"

        # Step b: Buyer selects a product that has sizes (Apparel: Classic Cotton Shirt)
        res_sel = _send_postback(
            client, user_id, "action=select_product&sku=SKU-SHIRT-01", reply_token="tok_2"
        )
        assert res_sel.status_code == 200
        assert mock_line_client.reply_message.call_count == 2
        size_prompt_reply = mock_line_client.reply_message.call_args[0][1][0]
        assert size_prompt_reply["type"] == "text"
        assert get_text("pick_size", "th", name="Classic Cotton Shirt") in size_prompt_reply["text"]
        # Verify size buttons/quick replies exist
        qr_items = size_prompt_reply["quickReply"]["items"]
        assert len(qr_items) == 4
        assert qr_items[0]["action"]["data"] == "action=select_size&sku=SKU-SHIRT-01&size=S"

        # Step c: Buyer selects size "M"
        res_size = _send_postback(
            client, user_id, "action=select_size&sku=SKU-SHIRT-01&size=M", reply_token="tok_3"
        )
        assert res_size.status_code == 200
        assert mock_line_client.reply_message.call_count == 3
        qty_prompt_reply = mock_line_client.reply_message.call_args[0][1][0]
        assert (
            get_text("enter_qty_with_size", "th", name="Classic Cotton Shirt", size="M")
            in qty_prompt_reply["text"]
        )

        # Step d: Buyer enters quantity 2
        res_qty = _send_postback(
            client, user_id, "action=set_qty&sku=SKU-SHIRT-01&size=M&qty=2", reply_token="tok_4"
        )
        assert res_qty.status_code == 200
        assert mock_line_client.reply_message.call_count == 4
        subtotal_reply = mock_line_client.reply_message.call_args[0][1][0]
        assert (
            get_text("line_subtotal", "th", name="Classic Cotton Shirt", qty=2, subtotal="980.00")
            in subtotal_reply["text"]
        )
        assert get_text("add_more_or_confirm", "th") in subtotal_reply["text"]

        # Step e: Buyer taps Confirm
        res_conf = _send_postback(client, user_id, "action=confirm_order", reply_token="tok_5")
        assert res_conf.status_code == 200
        assert mock_line_client.reply_message.call_count == 5
        replies = mock_line_client.reply_message.call_args[0][1]
        assert len(replies) == 2
        summary_text = replies[0]["text"]
        next_step_text = replies[1]["text"]
        assert "Classic Cotton Shirt (M) x2" in summary_text
        assert "980.00" in summary_text
        assert next_step_text == get_text("order_confirmed_next_step", "th")

        # Verify database state: order reaches ORDER_CONFIRMED
        orders = db_session.query(Order).filter(Order.line_user_id == user_id).all()
        assert len(orders) == 1
        order = orders[0]
        assert order.status == OrderStatus.ORDER_CONFIRMED.value
        assert order.total == Decimal("980.00")
        assert len(order.items) == 1
        item = order.items[0]
        assert item.sku == "SKU-SHIRT-01"
        assert item.size == "M"
        assert item.qty == 2
        assert item.unit_price == Decimal("490.00")
        assert item.line_total == Decimal("980.00")

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_full_guided_flow_without_size_reaches_order_confirmed(
    client: TestClient,
    db_session: Session,
    mock_line_client: LineClient,
    seed_catalog: list[Inventory],
):
    """
    Acceptance criterion 1 (§20):
    Product without sizes (e.g. Scarf) skips size step directly to quantity.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_buyer_nosize_01"

        # 1. Tap product without sizes (Accessories: Thai Silk Scarf)
        res_sel = _send_postback(
            client, user_id, "action=select_product&sku=SKU-SCARF-01", reply_token="tok_1"
        )
        assert res_sel.status_code == 200
        reply = mock_line_client.reply_message.call_args[0][1][0]
        # Should ask for qty directly (not size)
        assert get_text("enter_qty", "th", name="Thai Silk Scarf") in reply["text"]

        # 2. Set quantity = 3
        res_qty = _send_postback(
            client, user_id, "action=set_qty&sku=SKU-SCARF-01&qty=3", reply_token="tok_2"
        )
        assert res_qty.status_code == 200
        reply_qty = mock_line_client.reply_message.call_args[0][1][0]
        assert (
            get_text("line_subtotal", "th", name="Thai Silk Scarf", qty=3, subtotal="1,050.00")
            in reply_qty["text"]
        )

        # 3. Confirm order
        res_conf = _send_postback(client, user_id, "action=confirm_order", reply_token="tok_3")
        assert res_conf.status_code == 200

        order = db_session.query(Order).filter(Order.line_user_id == user_id).first()
        assert order is not None
        assert order.status == OrderStatus.ORDER_CONFIRMED.value
        assert order.total == Decimal("1050.00")
        assert order.items[0].size is None
        assert order.items[0].qty == 3

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_order_more_loop_returns_to_product_carousel_and_accumulates(
    client: TestClient,
    db_session: Session,
    mock_line_client: LineClient,
    seed_catalog: list[Inventory],
):
    """
    Acceptance criterion 2 (§20, TEST_PLAN.md):
    The 'Order more?' loop correctly returns to the product carousel and adds multiple items.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_buyer_multi_01"

        # Item 1: Thai Silk Scarf x1
        _send_postback(client, user_id, "action=select_product&sku=SKU-SCARF-01", reply_token="t1")
        _send_postback(client, user_id, "action=set_qty&sku=SKU-SCARF-01&qty=1", reply_token="t2")

        # Buyer taps 'Order more?' (action=add_more)
        res_more = _send_postback(client, user_id, "action=add_more", reply_token="t3")
        assert res_more.status_code == 200
        # Returned to product carousel
        carousel_reply = mock_line_client.reply_message.call_args[0][1][0]
        assert carousel_reply["type"] == "flex"
        assert carousel_reply["contents"]["type"] == "carousel"

        # Item 2: Shirt (Size L) x2
        _send_postback(client, user_id, "action=select_product&sku=SKU-SHIRT-01", reply_token="t4")
        _send_postback(
            client, user_id, "action=select_size&sku=SKU-SHIRT-01&size=L", reply_token="t5"
        )
        _send_postback(
            client, user_id, "action=set_qty&sku=SKU-SHIRT-01&size=L&qty=2", reply_token="t6"
        )

        # Confirm combined order
        _send_postback(client, user_id, "action=confirm_order", reply_token="t7")

        order = db_session.query(Order).filter(Order.line_user_id == user_id).first()
        assert order is not None
        assert order.status == OrderStatus.ORDER_CONFIRMED.value
        # Total: (350 * 1) + (490 * 2) = 350 + 980 = 1330.00
        assert order.total == Decimal("1330.00")
        assert len(order.items) == 2
        item_skus = {item.sku for item in order.items}
        assert item_skus == {"SKU-SCARF-01", "SKU-SHIRT-01"}

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_empty_cart_is_rejected_with_clean_message(
    client: TestClient,
    db_session: Session,
    mock_line_client: LineClient,
):
    """
    Required test (TEST_PLAN.md Phase 3):
    Empty cart is rejected with a clean message.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_buyer_empty_cart"

        # Buyer attempts to confirm order without having added any items
        res = _send_postback(client, user_id, "action=confirm_order", reply_token="tok_empty")
        assert res.status_code == 200

        assert mock_line_client.reply_message.call_count == 1
        reply = mock_line_client.reply_message.call_args[0][1][0]
        assert reply["text"] == get_text("empty_cart_error", "th")

        # Verify no confirmed order exists in DB
        orders = db_session.query(Order).filter(Order.line_user_id == user_id).all()
        assert len(orders) == 0

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_out_of_stock_item_is_rejected_cleanly_at_quantity_step(
    client: TestClient,
    db_session: Session,
    mock_line_client: LineClient,
    seed_catalog: list[Inventory],
):
    """
    Required test (TEST_PLAN.md Phase 3):
    Out-of-stock item is rejected cleanly at the quantity step.
    Product SKU-LOW-01 has stock=2. Buyer asks for qty=5.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_buyer_oos_qty"

        # Select product with 2 units available
        _send_postback(client, user_id, "action=select_product&sku=SKU-LOW-01", reply_token="t1")

        # Request 5 units (exceeds available stock of 2)
        res_qty = _send_postback(
            client, user_id, "action=set_qty&sku=SKU-LOW-01&qty=5", reply_token="t2"
        )
        assert res_qty.status_code == 200

        reply = mock_line_client.reply_message.call_args[0][1][0]
        assert reply["text"] == get_text("out_of_stock_error", "th")

        # Verify nothing was added to the order
        order = db_session.query(Order).filter(Order.line_user_id == user_id).first()
        if order:
            assert len(order.items) == 0

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_out_of_stock_item_rejected_at_selection(
    client: TestClient,
    db_session: Session,
    mock_line_client: LineClient,
    seed_catalog: list[Inventory],
):
    """
    Product with stock=0 (SKU-OUT-01) rejected immediately when tapped.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_buyer_zero_stock"

        res = _send_postback(
            client, user_id, "action=select_product&sku=SKU-OUT-01", reply_token="t1"
        )
        assert res.status_code == 200

        reply = mock_line_client.reply_message.call_args[0][1][0]
        assert reply["text"] == get_text("out_of_stock_error", "th")

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_invalid_quantity_rejected_cleanly(
    client: TestClient,
    mock_line_client: LineClient,
    seed_catalog: list[Inventory],
):
    """Invalid non-positive or non-numeric quantity rejected cleanly."""
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_buyer_invalid_qty"

        # Non-numeric
        _send_postback(client, user_id, "action=set_qty&sku=SKU-SCARF-01&qty=abc", reply_token="t1")
        reply = mock_line_client.reply_message.call_args[0][1][0]
        assert reply["text"] == get_text("invalid_qty_error", "th")

        # Zero
        _send_postback(client, user_id, "action=set_qty&sku=SKU-SCARF-01&qty=0", reply_token="t2")
        reply2 = mock_line_client.reply_message.call_args[0][1][0]
        assert reply2["text"] == get_text("invalid_qty_error", "th")

        # Negative
        _send_postback(client, user_id, "action=set_qty&sku=SKU-SCARF-01&qty=-3", reply_token="t3")
        reply3 = mock_line_client.reply_message.call_args[0][1][0]
        assert reply3["text"] == get_text("invalid_qty_error", "th")

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_quantity_entered_via_text_message(
    client: TestClient,
    db_session: Session,
    mock_line_client: LineClient,
    seed_catalog: list[Inventory],
):
    """
    Buyer selects product, then types number '2' in chat text instead of tapping button.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_buyer_text_qty"

        # Tap product
        _send_postback(client, user_id, "action=select_product&sku=SKU-SCARF-01", reply_token="t1")

        # Type text '2'
        res_text = _send_text(client, user_id, "2", reply_token="t2")
        assert res_text.status_code == 200

        reply = mock_line_client.reply_message.call_args[0][1][0]
        assert (
            get_text("line_subtotal", "th", name="Thai Silk Scarf", qty=2, subtotal="700.00")
            in reply["text"]
        )

        # Confirm
        _send_postback(client, user_id, "action=confirm_order", reply_token="t3")
        order = db_session.query(Order).filter(Order.line_user_id == user_id).first()
        assert order is not None
        assert order.total == Decimal("700.00")
        assert order.items[0].qty == 2

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_order_before_address_enforced_no_address_collection_in_phase3(
    client: TestClient,
    db_session: Session,
    mock_line_client: LineClient,
    seed_catalog: list[Inventory],
):
    """
    Order-before-address rule (§8, §9, §20):
    Order reaches ORDER_CONFIRMED before any address is collected.
    Phase 3 does NOT collect address; replies with order summary and next step hint.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_buyer_order_before_addr"

        _send_postback(client, user_id, "action=select_product&sku=SKU-SCARF-01", reply_token="t1")
        _send_postback(client, user_id, "action=set_qty&sku=SKU-SCARF-01&qty=1", reply_token="t2")
        _send_postback(client, user_id, "action=confirm_order", reply_token="t3")

        order = db_session.query(Order).filter(Order.line_user_id == user_id).first()
        assert order is not None
        assert order.status == OrderStatus.ORDER_CONFIRMED.value

        # Verify reply contains hint for Phase 4 address step without executing Phase 4 logic
        replies = mock_line_client.reply_message.call_args[0][1]
        next_step_reply = replies[1]["text"]
        assert next_step_reply == get_text("order_confirmed_next_step", "th")

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_bilingual_guided_ordering_english_preference(
    client: TestClient,
    db_session: Session,
    mock_line_client: LineClient,
    seed_catalog: list[Inventory],
):
    """
    Verify full guided ordering replies entirely in English when buyer preferred language is 'en'.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_buyer_english_pref"
        pref = UserPrefs(user_id=user_id, scope="buyer", language="en")
        db_session.add(pref)
        db_session.commit()

        # Step 1: Browse
        _send_postback(client, user_id, "action=browse", reply_token="t1")
        carousel_reply = mock_line_client.reply_message.call_args[0][1][0]
        assert carousel_reply["altText"] == get_text("carousel_title", "en")

        # Step 2: Select Apparel product -> size prompt in English
        _send_postback(client, user_id, "action=select_product&sku=SKU-SHIRT-01", reply_token="t2")
        size_reply = mock_line_client.reply_message.call_args[0][1][0]
        assert size_reply["text"] == get_text("pick_size", "en", name="Classic Cotton Shirt")

        # Step 3: Select size M -> qty prompt in English
        _send_postback(
            client, user_id, "action=select_size&sku=SKU-SHIRT-01&size=M", reply_token="t3"
        )
        qty_reply = mock_line_client.reply_message.call_args[0][1][0]
        assert size_reply["text"] == get_text("pick_size", "en", name="Classic Cotton Shirt")
        assert (
            get_text("enter_qty_with_size", "en", name="Classic Cotton Shirt", size="M")
            in qty_reply["text"]
        )

        # Step 4: Set qty 1 -> line subtotal in English
        _send_postback(
            client, user_id, "action=set_qty&sku=SKU-SHIRT-01&size=M&qty=1", reply_token="t4"
        )
        subtotal_reply = mock_line_client.reply_message.call_args[0][1][0]
        assert (
            get_text("line_subtotal", "en", name="Classic Cotton Shirt", qty=1, subtotal="490.00")
            in subtotal_reply["text"]
        )
        assert get_text("add_more_or_confirm", "en") in subtotal_reply["text"]

        # Step 5: Confirm -> English summary and next step hint
        _send_postback(client, user_id, "action=confirm_order", reply_token="t5")
        replies = mock_line_client.reply_message.call_args[0][1]
        assert "Order Summary" in replies[0]["text"]
        assert replies[1]["text"] == get_text("order_confirmed_next_step", "en")

    finally:
        app.dependency_overrides.pop(get_line_client, None)
