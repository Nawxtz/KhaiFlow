import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.webhook import clear_processed_events, get_line_client
from app.core.line_client import LineClient
from app.main import app

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
def reset_webhook_state():
    """Clear processed event IDs before each test."""
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


def test_webhook_rejects_missing_signature(client: TestClient):
    """TEST_PLAN.md: LINE webhook signature validation rejects any request without a signature."""
    payload = json.dumps({"events": []}).encode("utf-8")
    response = client.post("/line/webhook", content=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid LINE signature"


def test_webhook_rejects_invalid_signature(client: TestClient, mock_line_client):
    """TEST_PLAN.md: LINE webhook signature validation rejects any request with an invalid signature."""
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        payload = json.dumps({"events": []}).encode("utf-8")
        headers = {"X-Line-Signature": "invalid_signature_base64=="}
        response = client.post("/line/webhook", content=payload, headers=headers)
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid LINE signature"
    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_webhook_accepts_valid_signature(client: TestClient, mock_line_client):
    """Verify webhook accepts valid HMAC signature and processes events."""
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        payload_dict = {
            "destination": "U_test_bot",
            "events": [
                {
                    "webhookEventId": "evt_valid_001",
                    "type": "message",
                    "timestamp": 1695432000000,
                    "source": {"type": "user", "userId": "U_valid_user"},
                    "replyToken": "reply_token_001",
                    "message": {"id": "msg_001", "type": "text", "text": "Hello"},
                }
            ],
        }
        body = json.dumps(payload_dict).encode("utf-8")
        headers = {"X-Line-Signature": generate_line_signature(body, TEST_SECRET)}

        response = client.post("/line/webhook", content=body, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert mock_line_client.reply_message.call_count == 1
    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_duplicate_webhook_event_is_ignored_idempotently(client: TestClient, mock_line_client):
    """
    TEST_PLAN.md: Duplicate LINE webhook event (same webhookEventId) is ignored idempotently.
    The second invocation returns 200 but does not re-reply.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        payload_dict = {
            "events": [
                {
                    "webhookEventId": "evt_idempotent_001",
                    "type": "message",
                    "timestamp": 1695432000000,
                    "source": {"type": "user", "userId": "U_idem_user"},
                    "replyToken": "reply_token_idem",
                    "message": {"id": "msg_idem", "type": "text", "text": "Hi"},
                }
            ]
        }
        body = json.dumps(payload_dict).encode("utf-8")
        headers = {"X-Line-Signature": generate_line_signature(body, TEST_SECRET)}

        # First delivery -> processes event, calls reply_message
        res1 = client.post("/line/webhook", content=body, headers=headers)
        assert res1.status_code == 200
        assert mock_line_client.reply_message.call_count == 1

        # Second delivery (duplicate webhookEventId) -> returns 200, does NOT call reply_message again
        res2 = client.post("/line/webhook", content=body, headers=headers)
        assert res2.status_code == 200
        assert mock_line_client.reply_message.call_count == 1
    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_unsupported_webhook_event_types_safely_ignored(client: TestClient, mock_line_client):
    """
    TEST_PLAN.md: Unsupported webhook event types are safely ignored.
    Should return 200, not crash, and not invoke handler actions.
    """
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        unsupported_events = ["beacon", "accountLink", "memberJoined", "unsupported_custom_type"]
        for idx, event_type in enumerate(unsupported_events):
            payload_dict = {
                "events": [
                    {
                        "webhookEventId": f"evt_unsupported_{idx}",
                        "type": event_type,
                        "timestamp": 1695432000000,
                        "source": {"type": "user", "userId": "U_test_user"},
                    }
                ]
            }
            body = json.dumps(payload_dict).encode("utf-8")
            headers = {"X-Line-Signature": generate_line_signature(body, TEST_SECRET)}

            response = client.post("/line/webhook", content=body, headers=headers)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

        assert mock_line_client.reply_message.call_count == 0
    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_malformed_json_payload_rejected(client: TestClient, mock_line_client):
    """Malformed webhook payload returns 400 Bad Request."""
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        body = b"not-a-valid-json-string"
        headers = {"X-Line-Signature": generate_line_signature(body, TEST_SECRET)}

        response = client.post("/line/webhook", content=body, headers=headers)
        assert response.status_code == 400
        assert "Malformed webhook payload" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_line_client, None)
