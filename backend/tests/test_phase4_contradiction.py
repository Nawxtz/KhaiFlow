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
from app.models.order import Order, OrderStatus
from app.services.address_engine import (
    check_contradiction,
    set_parser,
)
from app.services.address_session import clear_all_address_sessions, get_address_session
from app.services.i18n import get_text

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


def test_contradiction_detection_bangkok_zip_with_chiangmai_province():
    """
    Unit check for check_contradiction helper:
    Bangkok 10200 vs Chiang Mai must be detected as a contradiction.
    """
    # Explicit mismatch: 10200 is Bangkok (Phra Nakhon), not Chiang Mai
    conflict = check_contradiction(postcode="10200", province="เชียงใหม่")
    assert conflict is not None
    assert conflict["postcode"] == "10200"
    assert conflict["province"] == "เชียงใหม่"

    # Consistent case: 10200 is Bangkok
    no_conflict = check_contradiction(postcode="10200", province="กรุงเทพมหานคร")
    assert no_conflict is None


def test_contradiction_flow_flags_disambiguation_prompt_and_resolves(
    client: TestClient,
    db_session: Session,
):
    """
    Critical Reviewer Acceptance Test:
    1. Input address contains Bangkok postcode 10200 with Chiang Mai province.
    2. Bot replies with disambiguation prompt showing BOTH values (NOT silent pick or crash).
    3. User selects province -> bot clears conflicting zip and asks for correct zip.
    4. User provides Chiang Mai zip (50000) -> proceeds to dry run.
    """
    mock_line_client = MagicMock(spec=LineClient)
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_contradiction_buyer_01"

        # Seed confirmed order awaiting address
        order = Order(
            id="ORD-CONTRA-01",
            line_user_id=user_id,
            status=OrderStatus.ORDER_CONFIRMED.value,
        )
        db_session.add(order)
        db_session.commit()

        # Mock parser returning the contradictory address
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {
            "receiver": "Somchai Sailom",
            "phone": "0812345678",
            "address_detail": "123/45 Nimman Road",
            "sub_district": "Suthep",
            "district": "Mueang",
            "province": "เชียงใหม่",
            "zipcode": "10200",
            "confidence": 0.70,
            "warnings": ["geographic_mismatch"],
        }
        set_parser(mock_parser)

        # 1. Buyer enters contradictory address text
        res = _send_text(
            client, user_id, "Somchai 0812345678 123/45 เชียงใหม่ 10200", reply_token="t1"
        )
        assert res.status_code == 200

        # Verify bot replied with disambiguation prompt showing BOTH values
        replies = mock_line_client.reply_message.call_args[0][1]
        prompt_reply = replies[0]

        # Verify BOTH values appear in the prompt text
        assert "10200" in prompt_reply["text"]
        assert "เชียงใหม่" in prompt_reply["text"]

        # Verify quick reply buttons offer both choices
        quick_items = prompt_reply["quickReply"]["items"]
        assert len(quick_items) == 2
        datas = [item["action"]["data"] for item in quick_items]
        assert any("choice=postcode" in d and "10200" in d for d in datas)
        assert any("choice=province" in d and "เชียงใหม่" in d for d in datas)

        # Order must be in ADDRESS_COLLECTION
        db_session.refresh(order)
        assert order.status == OrderStatus.ADDRESS_COLLECTION.value

        # Session must be in CONTRADICTION state
        session = get_address_session(user_id)
        assert session is not None
        assert session.status == "CONTRADICTION"

        # 2. Buyer resolves by picking province (Chiang Mai)
        res_pb = _send_postback(
            client,
            user_id,
            "action=resolve_contradiction&choice=province&val=เชียงใหม่",
            reply_token="t2",
        )
        assert res_pb.status_code == 200

        # Bot asks for missing postcode
        reply_missing = mock_line_client.reply_message.call_args[0][1][0]
        assert reply_missing["text"] == get_text("enter_missing_postcode", "th")

        # 3. Buyer provides correct Chiang Mai postcode 50000
        res_zip = _send_text(client, user_id, "50000", reply_token="t3")
        assert res_zip.status_code == 200

        # All fields complete -> dry run summary displayed
        reply_dry_run = mock_line_client.reply_message.call_args[0][1][0]
        assert "quickReply" in reply_dry_run
        actions = [i["action"]["data"] for i in reply_dry_run["quickReply"]["items"]]
        assert "action=address_confirm" in actions
        assert "action=address_edit" in actions

    finally:
        app.dependency_overrides.pop(get_line_client, None)
