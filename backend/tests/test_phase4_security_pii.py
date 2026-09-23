import base64
import hashlib
import hmac
import json
import logging
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.webhook import clear_processed_events, get_line_client
from app.core.line_client import LineClient
from app.main import app
from app.models.order import Order, OrderStatus
from app.services.address_engine import set_parser
from app.services.address_session import clear_all_address_sessions

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


def test_no_personal_data_leaks_into_logs_during_address_flow(
    client: TestClient,
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
):
    """
    TEST_PLAN.md & Definition of Done:
    No personal data (name, phone, full address) appears in logs.
    Executes full address parsing, slot-filling, and confirmation while capturing all logs.
    """
    mock_line_client = MagicMock(spec=LineClient)
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_pii_check_user"

        order = Order(
            id="ORD-PII-01",
            line_user_id=user_id,
            status=OrderStatus.ORDER_CONFIRMED.value,
        )
        db_session.add(order)
        db_session.commit()

        # Sensitive mock customer personal data
        sensitive_name = "SecretCustomerNameX"
        sensitive_phone = "0891999999"
        sensitive_street = "777 Top Secret Boulevard"
        sensitive_full_addr = (
            "SecretCustomerNameX 0891999999 777 Top Secret Boulevard Bangkok 10110"
        )

        mock_parser = MagicMock()
        mock_parser.parse.return_value = {
            "receiver": sensitive_name,
            "phone": sensitive_phone,
            "address_detail": sensitive_street,
            "sub_district": "Khlong Toei",
            "district": "Khlong Toei",
            "province": "กรุงเทพมหานคร",
            "zipcode": "10110",
            "confidence": 0.95,
            "warnings": [],
        }
        set_parser(mock_parser)

        with caplog.at_level(logging.DEBUG):
            # 1. Send address text
            _send_text(client, user_id, sensitive_full_addr, reply_token="t1")

            # 2. Confirm address
            _send_postback(client, user_id, "action=address_confirm", reply_token="t2")

        # Inspect all captured logs
        captured_log_text = " ".join([record.getMessage() for record in caplog.records])

        # Assert no sensitive personal data appears in logs
        assert sensitive_name not in captured_log_text, "Receiver name leaked into logs!"
        assert sensitive_phone not in captured_log_text, "Phone number leaked into logs!"
        assert sensitive_street not in captured_log_text, "Street address leaked into logs!"

    finally:
        app.dependency_overrides.pop(get_line_client, None)
