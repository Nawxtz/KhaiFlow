import base64
import hashlib
import hmac
import json
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

from app.core.line_client import LineClient

FAKE_LINE_SECRET = "fake_channel_secret_for_tests"


class FakeLineClient(LineClient):
    """LineClient that records every outbound call and never reaches the network."""

    def __init__(self) -> None:
        super().__init__(channel_access_token="fake_access_token", channel_secret=FAKE_LINE_SECRET)
        self.replies: list[tuple[str, Any]] = []
        self.pushes: list[tuple[str, Any]] = []

    def reply_message(
        self,
        reply_token: str,
        messages: list[dict[str, Any]] | dict[str, Any],
    ) -> None:
        self.replies.append((reply_token, messages))

    def push_message(
        self,
        to: str,
        messages: list[dict[str, Any]] | dict[str, Any],
    ) -> None:
        self.pushes.append((to, messages))

    def create_rich_menu(self, rich_menu_data: dict[str, Any]) -> str:
        return "fake_rich_menu_id"

    def link_rich_menu_to_user(self, user_id: str, rich_menu_id: str) -> None:
        return None


def text_event(
    event_id: str,
    text: str,
    user_id: str = "U_fake_buyer",
    reply_token: str = "fake_reply_token",
) -> dict[str, Any]:
    """Build a LINE text-message webhook event."""
    return {
        "webhookEventId": event_id,
        "type": "message",
        "timestamp": 1695432000000,
        "source": {"type": "user", "userId": user_id},
        "replyToken": reply_token,
        "message": {"id": f"msg_{event_id}", "type": "text", "text": text},
    }


def sign_line_body(body: bytes, secret: str = FAKE_LINE_SECRET) -> str:
    """Return the X-Line-Signature value for a webhook body."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def post_line_events(
    client: TestClient,
    events: list[dict[str, Any]],
    secret: str = FAKE_LINE_SECRET,
) -> Response:
    """POST events to the LINE webhook, signed with the given secret."""
    body = json.dumps({"destination": "U_fake_bot", "events": events}).encode("utf-8")
    return client.post(
        "/line/webhook",
        content=body,
        headers={"X-Line-Signature": sign_line_body(body, secret)},
    )
