import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.webhook import clear_processed_events, get_line_client
from app.core.line_client import LineClient
from app.main import app
from app.models.address_book import AddressBook
from app.models.order import Order, OrderStatus
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


def test_high_confidence_complete_address_skips_slot_filling(
    client: TestClient,
    db_session: Session,
):
    """
    TEST_PLAN.md: High-confidence, complete address -> confirms without slot-filling.
    Goes directly to dry-run summary.
    """
    mock_line_client = MagicMock(spec=LineClient)
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_high_conf_buyer"

        order = Order(
            id="ORD-HIGH-CONF-01",
            line_user_id=user_id,
            status=OrderStatus.ORDER_CONFIRMED.value,
        )
        db_session.add(order)
        db_session.commit()

        # Mock high-confidence parser
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {
            "receiver": "Kanya Prasert",
            "phone": "0899998888",
            "address_detail": "555 Phahonyothin Rd",
            "sub_district": "Chatuchak",
            "district": "Chatuchak",
            "province": "กรุงเทพมหานคร",
            "zipcode": "10900",
            "confidence": 0.95,
            "warnings": [],
        }
        set_parser(mock_parser)

        res = _send_text(
            client,
            user_id,
            "Kanya 0899998888 555 Phahonyothin Chatuchak Bangkok 10900",
            reply_token="t1",
        )
        assert res.status_code == 200

        # Verify: directly to dry-run, no missing field questions
        reply = mock_line_client.reply_message.call_args[0][1][0]
        assert "quickReply" in reply
        quick_actions = [i["action"]["data"] for i in reply["quickReply"]["items"]]
        assert "action=address_confirm" in quick_actions
        assert "action=address_edit" in quick_actions

        session = get_address_session(user_id)
        assert session is not None
        assert session.status == "DRY_RUN"
        assert session.pending_field is None

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_incomplete_address_loops_asking_only_missing_fields(
    client: TestClient,
    db_session: Session,
):
    """
    TEST_PLAN.md: Incomplete address -> loops asking only the missing fields.
    1. Buyer enters address missing phone and postcode.
    2. Bot asks for missing phone.
    3. Buyer inputs phone -> Bot asks for missing postcode.
    4. Buyer inputs postcode -> Bot shows dry-run summary.
    """
    mock_line_client = MagicMock(spec=LineClient)
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_incomplete_buyer"

        order = Order(
            id="ORD-INCOMP-01",
            line_user_id=user_id,
            status=OrderStatus.ORDER_CONFIRMED.value,
        )
        db_session.add(order)
        db_session.commit()

        # Mock parser returning address missing phone and zipcode
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {
            "receiver": "Prasert Suk",
            "phone": None,
            "address_detail": "12/3 Sukhumvit 71",
            "sub_district": "Phra Khanong Nuea",
            "district": "Watthana",
            "province": "กรุงเทพมหานคร",
            "zipcode": None,
            "confidence": 0.65,
            "warnings": ["missing_phone", "missing_zipcode"],
        }
        set_parser(mock_parser)

        # 1. Buyer enters incomplete address
        res1 = _send_text(
            client, user_id, "Prasert 12/3 Sukhumvit 71 Watthana Bangkok", reply_token="t1"
        )
        assert res1.status_code == 200

        # Bot asks for FIRST missing field: phone
        reply1 = mock_line_client.reply_message.call_args[0][1][0]
        assert reply1["text"] == get_text("enter_missing_phone", "th")

        session = get_address_session(user_id)
        assert session is not None
        assert session.pending_field == "phone"

        # 2. Buyer sends phone number
        res2 = _send_text(client, user_id, "0819876543", reply_token="t2")
        assert res2.status_code == 200

        # Bot asks for NEXT missing field: postcode
        reply2 = mock_line_client.reply_message.call_args[0][1][0]
        assert reply2["text"] == get_text("enter_missing_postcode", "th")

        session = get_address_session(user_id)
        assert session.collected_fields["phone"] == "0819876543"
        assert session.pending_field == "postcode"

        # 3. Buyer sends postcode
        res3 = _send_text(client, user_id, "10110", reply_token="t3")
        assert res3.status_code == 200

        # All fields complete -> dry run summary shown
        reply3 = mock_line_client.reply_message.call_args[0][1][0]
        assert "quickReply" in reply3
        actions = [i["action"]["data"] for i in reply3["quickReply"]["items"]]
        assert "action=address_confirm" in actions
        assert "action=address_edit" in actions

        session = get_address_session(user_id)
        assert session.status == "DRY_RUN"
        assert session.collected_fields["postcode"] == "10110"
        assert session.pending_field is None

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_returning_buyer_saved_address_choice_flow(
    client: TestClient,
    db_session: Session,
):
    """
    Returning Buyer Flow:
    1. Returning buyer has saved address in address_book.
    2. Bot offers saved address choice upon order confirmation.
    3. Buyer taps [use_saved_address]: skips slot-filling, directly presents dry-run.
    """
    mock_line_client = MagicMock(spec=LineClient)
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_returning_buyer_01"

        # Seed saved address
        saved_addr = AddressBook(
            line_user_id=user_id,
            receiver_name="Returning Buyer",
            phone="0897776655",
            address_json={
                "receiver_name": "Returning Buyer",
                "phone": "0897776655",
                "house_number": "99/1",
                "street": "Rama 4 Road",
                "subdistrict": "Khlong Toei",
                "district": "Khlong Toei",
                "province": "กรุงเทพมหานคร",
                "postcode": "10110",
                "full_address": "99/1 Rama 4 Road Khlong Toei Khlong Toei Bangkok 10110",
            },
            is_default=True,
        )
        db_session.add(saved_addr)

        # Seed order
        order = Order(
            id="ORD-RETURNING-01",
            line_user_id=user_id,
            status=OrderStatus.ORDER_CONFIRMED.value,
        )
        db_session.add(order)
        db_session.commit()

        # 1. Buyer taps [use_saved_address] postback
        res = _send_postback(
            client,
            user_id,
            f"action=use_saved_address&address_id={saved_addr.id}",
            reply_token="t1",
        )
        assert res.status_code == 200

        # Verify slot-filling was skipped, directly showing dry-run summary
        reply = mock_line_client.reply_message.call_args[0][1][0]
        assert "quickReply" in reply
        actions = [i["action"]["data"] for i in reply["quickReply"]["items"]]
        assert "action=address_confirm" in actions
        assert "action=address_edit" in actions

        session = get_address_session(user_id)
        assert session is not None
        assert session.status == "DRY_RUN"
        assert session.collected_fields["receiver_name"] == "Returning Buyer"
        assert session.collected_fields["postcode"] == "10110"

        # 2. Buyer confirms saved address
        res_conf = _send_postback(client, user_id, "action=address_confirm", reply_token="t2")
        assert res_conf.status_code == 200

        db_session.refresh(order)
        assert order.status == OrderStatus.ADDRESS_CONFIRMED.value

    finally:
        app.dependency_overrides.pop(get_line_client, None)
