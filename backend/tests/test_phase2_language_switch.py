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
from app.models.user_prefs import UserPrefs
from app.services.i18n import get_text
from tests.test_phase2_webhook import TEST_SECRET, generate_line_signature


@pytest.fixture(autouse=True)
def reset_webhook_state():
    clear_processed_events()
    yield
    clear_processed_events()


@pytest.fixture
def mock_line_client():
    client = LineClient(
        channel_access_token="test_access_token",
        channel_secret=TEST_SECRET,
    )
    client.reply_message = MagicMock()
    return client


def _send_webhook(client: TestClient, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    headers = {"X-Line-Signature": generate_line_signature(body, TEST_SECRET)}
    res = client.post("/line/webhook", content=body, headers=headers)
    assert res.status_code == 200


def test_language_switch_mid_conversation_reflected_in_very_next_message(
    client: TestClient,
    db_session: Session,
    mock_line_client,
):
    """
    TEST_PLAN.md: Language switch mid-conversation is reflected in the very next bot message.
    Verifies:
    1. Initial text message gets Thai reply (shop default).
    2. Postback action=set_lang&lang=en switches user_prefs to English.
    3. The VERY NEXT bot message uses English from en.json.
    4. Subsequent text messages also use English.
    5. Switching back to Thai immediately reflects in the very next message.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_bilingual_buyer_001"

        # Step 1: Initial user message -> Bot replies in default Thai
        _send_webhook(
            client,
            {
                "events": [
                    {
                        "webhookEventId": "evt_msg_1",
                        "type": "message",
                        "source": {"type": "user", "userId": user_id},
                        "replyToken": "token_1",
                        "message": {"type": "text", "text": "Hello"},
                    }
                ]
            },
        )
        assert mock_line_client.reply_message.call_count == 1
        reply_args = mock_line_client.reply_message.call_args[0]
        assert reply_args[0] == "token_1"
        assert reply_args[1][0]["text"] == get_text("welcome", "th")

        # Step 2: Language switch postback -> Switch to English
        _send_webhook(
            client,
            {
                "events": [
                    {
                        "webhookEventId": "evt_postback_lang_en",
                        "type": "postback",
                        "source": {"type": "user", "userId": user_id},
                        "replyToken": "token_2",
                        "postback": {"data": "action=set_lang&lang=en"},
                    }
                ]
            },
        )
        # Verify DB updated
        pref = (
            db_session.query(UserPrefs)
            .filter(UserPrefs.user_id == user_id, UserPrefs.scope == "buyer")
            .first()
        )
        assert pref is not None
        assert pref.language == "en"

        # Verify the VERY NEXT message was in English
        assert mock_line_client.reply_message.call_count == 2
        reply_args2 = mock_line_client.reply_message.call_args[0]
        assert reply_args2[0] == "token_2"
        assert reply_args2[1][0]["text"] == get_text("language_changed", "en")
        assert "Language has been changed to English" in reply_args2[1][0]["text"]

        # Step 3: Next message from user -> uses English
        _send_webhook(
            client,
            {
                "events": [
                    {
                        "webhookEventId": "evt_msg_2",
                        "type": "message",
                        "source": {"type": "user", "userId": user_id},
                        "replyToken": "token_3",
                        "message": {"type": "text", "text": "Show menu"},
                    }
                ]
            },
        )
        assert mock_line_client.reply_message.call_count == 3
        reply_args3 = mock_line_client.reply_message.call_args[0]
        assert reply_args3[0] == "token_3"
        assert reply_args3[1][0]["text"] == get_text("welcome", "en")
        assert "Welcome to our shop!" in reply_args3[1][0]["text"]

        # Step 4: Switch back to Thai
        _send_webhook(
            client,
            {
                "events": [
                    {
                        "webhookEventId": "evt_postback_lang_th",
                        "type": "postback",
                        "source": {"type": "user", "userId": user_id},
                        "replyToken": "token_4",
                        "postback": {"data": "action=set_lang&lang=th"},
                    }
                ]
            },
        )
        # Verify DB updated
        db_session.expire_all()
        pref_th = (
            db_session.query(UserPrefs)
            .filter(UserPrefs.user_id == user_id, UserPrefs.scope == "buyer")
            .first()
        )
        assert pref_th is not None
        assert pref_th.language == "th"

        # Verify immediate reply is in Thai
        assert mock_line_client.reply_message.call_count == 4
        reply_args4 = mock_line_client.reply_message.call_args[0]
        assert reply_args4[0] == "token_4"
        assert reply_args4[1][0]["text"] == get_text("language_changed", "th")
        assert "เปลี่ยนภาษาเป็นภาษาไทยเรียบร้อยแล้ว" in reply_args4[1][0]["text"]

        # Step 5: Next message from user -> uses Thai
        _send_webhook(
            client,
            {
                "events": [
                    {
                        "webhookEventId": "evt_msg_3",
                        "type": "message",
                        "source": {"type": "user", "userId": user_id},
                        "replyToken": "token_5",
                        "message": {"type": "text", "text": "สวัสดีอีกครั้ง"},
                    }
                ]
            },
        )
        assert mock_line_client.reply_message.call_count == 5
        reply_args5 = mock_line_client.reply_message.call_args[0]
        assert reply_args5[0] == "token_5"
        assert reply_args5[1][0]["text"] == get_text("welcome", "th")
    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_language_switch_influences_browse_carousel(
    client: TestClient,
    db_session: Session,
    mock_line_client,
):
    """Verify browsing carousel respects active buyer language."""
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_carousel_buyer_002"

        # Insert a sample inventory item
        item = Inventory(
            sku="SKU-CAROUSEL-01",
            name="Silk Scarf",
            category="Accessories",
            price=Decimal("500.00"),
            image_url="https://example.com/scarf.jpg",
            stock=10,
            active=True,
        )
        db_session.add(item)
        db_session.commit()

        # Set user language to English
        pref = UserPrefs(user_id=user_id, scope="buyer", language="en")
        db_session.add(pref)
        db_session.commit()

        # Trigger browse postback
        _send_webhook(
            client,
            {
                "events": [
                    {
                        "webhookEventId": "evt_browse_en",
                        "type": "postback",
                        "source": {"type": "user", "userId": user_id},
                        "replyToken": "token_browse",
                        "postback": {"data": "action=browse"},
                    }
                ]
            },
        )

        assert mock_line_client.reply_message.call_count == 1
        reply_msg = mock_line_client.reply_message.call_args[0][1][0]
        assert reply_msg["type"] == "flex"
        assert reply_msg["altText"] == get_text("carousel_title", "en")

        # Check button label in carousel bubble
        carousel_bubble = reply_msg["contents"]["contents"][0]
        button_label = carousel_bubble["footer"]["contents"][0]["action"]["label"]
        assert button_label == get_text("btn_buy_now", "en")
        assert button_label == "Buy Now"
    finally:
        app.dependency_overrides.pop(get_line_client, None)
