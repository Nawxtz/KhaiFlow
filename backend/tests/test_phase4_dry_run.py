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
from app.models.address_book import AddressBook
from app.models.order import Order, OrderItem, OrderStatus
from app.services.address_engine import set_parser
from app.services.address_session import clear_all_address_sessions, get_address_session
from app.services.i18n import get_text

TEST_SECRET = "test_channel_secret_key_12345"


def generate_line_signature(body: bytes, secret: str = TEST_SECRET) -> str:
    computed_mac = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(computed_mac).decode("utf-8")


@pytest.fixture(autouse=True)
def setup_teardown():
    clear_processed_events()
    clear_all_address_sessions()
    yield
    clear_processed_events()
    clear_all_address_sessions()
    set_parser(None)


def _send_text(client: TestClient, user_id: str, text: str, reply_token: str = "t_txt"):
    payload = {
        "events": [
            {
                "webhookEventId": f"wh_{user_id}_{reply_token}",
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


def _send_postback(client: TestClient, user_id: str, data: str, reply_token: str = "t_pb"):
    payload = {
        "events": [
            {
                "webhookEventId": f"wh_pb_{user_id}_{reply_token}",
                "type": "postback",
                "source": {"type": "user", "userId": user_id},
                "replyToken": reply_token,
                "postback": {"data": data},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"X-Line-Signature": generate_line_signature(body, TEST_SECRET)}
    return client.post("/line/webhook", content=body, headers=headers)


def test_dry_run_correct_path_saves_address_and_confirms_order(
    client: TestClient,
    db_session: Session,
):
    """
    Reviewer Requirement:
    Dry-run [Correct] path works:
    - Order transitions to ADDRESS_CONFIRMED.
    - Address components saved to address_book table in address_json (JSONB).
    - Bot replies with confirmation message.
    """
    mock_line_client = MagicMock(spec=LineClient)
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_dryrun_correct_buyer"

        # Seed confirmed order awaiting address
        order = Order(
            id="ORD-DRYRUN-CORRECT-01",
            line_user_id=user_id,
            status=OrderStatus.ORDER_CONFIRMED.value,
            total=Decimal("450.00"),
        )
        item = OrderItem(
            order_id=order.id,
            sku="SKU-001",
            name="Thai Silk Scarf",
            qty=1,
            unit_price=Decimal("450.00"),
            line_total=Decimal("450.00"),
        )
        order.items.append(item)
        db_session.add(order)
        db_session.commit()

        # Mock high-confidence parser
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {
            "receiver": "Wichai Wattana",
            "phone": "0891234567",
            "address_detail": "88/9 Rama 9 Road",
            "sub_district": "Huai Khwang",
            "district": "Huai Khwang",
            "province": "กรุงเทพมหานคร",
            "zipcode": "10310",
            "confidence": 0.95,
            "warnings": [],
        }
        set_parser(mock_parser)

        # 1. Buyer enters complete address
        res_addr = _send_text(
            client,
            user_id,
            "Wichai 0891234567 88/9 Rama 9 Huai Khwang Bangkok 10310",
            reply_token="t1",
        )
        assert res_addr.status_code == 200

        # Verify dry run summary shown with [Correct] and [Edit] buttons
        reply = mock_line_client.reply_message.call_args[0][1][0]
        assert "quickReply" in reply
        quick_actions = [i["action"]["data"] for i in reply["quickReply"]["items"]]
        assert "action=address_confirm" in quick_actions
        assert "action=address_edit" in quick_actions

        # Verify order transitioned to ADDRESS_COLLECTION
        db_session.refresh(order)
        assert order.status == OrderStatus.ADDRESS_COLLECTION.value

        # 2. Buyer taps [Correct]
        res_confirm = _send_postback(client, user_id, "action=address_confirm", reply_token="t2")
        assert res_confirm.status_code == 200

        # Verify bot confirmed address
        reply_confirm = mock_line_client.reply_message.call_args[0][1][0]
        assert reply_confirm["text"] == get_text("address_confirmed", "th")

        # Verify order transitioned to ADDRESS_CONFIRMED
        db_session.refresh(order)
        assert order.status == OrderStatus.ADDRESS_CONFIRMED.value

        # Verify address saved in address_book table
        saved_addr = (
            db_session.query(AddressBook).filter(AddressBook.line_user_id == user_id).first()
        )
        assert saved_addr is not None
        assert saved_addr.receiver_name == "Wichai Wattana"
        assert saved_addr.phone == "0891234567"
        assert saved_addr.is_default is True
        assert saved_addr.address_json["postcode"] == "10310"
        assert saved_addr.address_json["subdistrict"] == "Huai Khwang"
        assert saved_addr.address_json["district"] == "Huai Khwang"

        # Verify address session cleared
        assert get_address_session(user_id) is None

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_dry_run_edit_path_resets_address_and_preserves_order_items(
    client: TestClient,
    db_session: Session,
):
    """
    Reviewer Requirement:
    Dry-run [Edit] path works:
    - Resets address slot-filling state for the current address only.
    - Draft order context and its line items are PRESERVED (not dropped or altered).
    - Order state stays/loops in ADDRESS_COLLECTION.
    - Bot sends restart prompt.
    """
    mock_line_client = MagicMock(spec=LineClient)
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_dryrun_edit_buyer"

        # Seed confirmed order with items
        order = Order(
            id="ORD-DRYRUN-EDIT-01",
            line_user_id=user_id,
            status=OrderStatus.ORDER_CONFIRMED.value,
            total=Decimal("700.00"),
        )
        item1 = OrderItem(
            order_id=order.id,
            sku="SKU-001",
            name="Thai Silk Scarf",
            qty=1,
            unit_price=Decimal("350.00"),
            line_total=Decimal("350.00"),
        )
        item2 = OrderItem(
            order_id=order.id,
            sku="SKU-002",
            name="Ceramic Cup",
            qty=1,
            unit_price=Decimal("350.00"),
            line_total=Decimal("350.00"),
        )
        order.items.extend([item1, item2])
        db_session.add(order)
        db_session.commit()

        # Mock address parser
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {
            "receiver": "Old Receiver",
            "phone": "0811111111",
            "address_detail": "10 Old Road",
            "sub_district": "Silom",
            "district": "Bang Rak",
            "province": "กรุงเทพมหานคร",
            "zipcode": "10500",
            "confidence": 0.90,
            "warnings": [],
        }
        set_parser(mock_parser)

        # 1. Buyer enters address -> reaches dry run
        _send_text(client, user_id, "Old address text", reply_token="t1")
        db_session.refresh(order)
        assert order.status == OrderStatus.ADDRESS_COLLECTION.value

        session = get_address_session(user_id)
        assert session is not None
        assert session.status == "DRY_RUN"
        assert session.collected_fields["receiver_name"] == "Old Receiver"

        # 2. Buyer taps [Edit]
        res_edit = _send_postback(client, user_id, "action=address_edit", reply_token="t2")
        assert res_edit.status_code == 200

        # Verify bot replies with restart prompt
        reply_edit = mock_line_client.reply_message.call_args[0][1][0]
        assert reply_edit["text"] == get_text("address_edit_restart", "th")

        # Verify order state machine: stays in ADDRESS_COLLECTION
        db_session.refresh(order)
        assert order.status == OrderStatus.ADDRESS_COLLECTION.value

        # CRITICAL: Verify draft order items are PRESERVED
        assert len(order.items) == 2
        assert order.total == Decimal("700.00")
        assert order.items[0].sku == "SKU-001"
        assert order.items[1].sku == "SKU-002"

        # Verify address slot-filling was reset
        session_after = get_address_session(user_id)
        assert session_after is not None
        assert session_after.status == "COLLECTING"
        assert len(session_after.collected_fields) == 0

        # 3. Buyer enters new corrected address
        mock_parser.parse.return_value = {
            "receiver": "New Receiver",
            "phone": "0822222222",
            "address_detail": "20 New Road",
            "sub_district": "Sathorn",
            "district": "Sathorn",
            "province": "กรุงเทพมหานคร",
            "zipcode": "10120",
            "confidence": 0.90,
            "warnings": [],
        }
        res_new = _send_text(client, user_id, "New address text", reply_token="t3")
        assert res_new.status_code == 200

        # Verify new dry run summary is shown
        reply_new = mock_line_client.reply_message.call_args[0][1][0]
        assert "quickReply" in reply_new

        # 4. Buyer taps [Correct] on new address
        res_confirm = _send_postback(client, user_id, "action=address_confirm", reply_token="t4")
        assert res_confirm.status_code == 200

        # Order transitions to ADDRESS_CONFIRMED with items intact
        db_session.refresh(order)
        assert order.status == OrderStatus.ADDRESS_CONFIRMED.value
        assert len(order.items) == 2
        assert order.total == Decimal("700.00")

        # Address saved is the NEW address
        saved_addr = (
            db_session.query(AddressBook).filter(AddressBook.line_user_id == user_id).first()
        )
        assert saved_addr is not None
        assert saved_addr.receiver_name == "New Receiver"
        assert saved_addr.phone == "0822222222"
        assert saved_addr.address_json["postcode"] == "10120"

    finally:
        app.dependency_overrides.pop(get_line_client, None)
