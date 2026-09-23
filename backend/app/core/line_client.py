import base64
import hashlib
import hmac
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class LineClient:
    """Wrapper for LINE Messaging API operations and webhook validation."""

    def __init__(
        self,
        channel_access_token: str | None = None,
        channel_secret: str | None = None,
    ):
        self.channel_access_token = channel_access_token or settings.LINE_CHANNEL_ACCESS_TOKEN
        self.channel_secret = channel_secret or settings.LINE_CHANNEL_SECRET

    def validate_signature(self, body: bytes, signature: str | None) -> bool:
        """
        Validate LINE webhook X-Line-Signature header.
        Uses HMAC-SHA256 with the channel secret.
        """
        if not signature or not self.channel_secret:
            return False

        try:
            computed_mac = hmac.new(
                self.channel_secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).digest()
            expected_signature = base64.b64encode(computed_mac).decode("utf-8")
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error("Error validating LINE signature: %s", e)
            return False

    def reply_message(
        self,
        reply_token: str,
        messages: list[dict[str, Any]] | dict[str, Any],
    ) -> None:
        """
        Reply to a LINE event using reply_token.
        In production, calls LINE Messaging API.
        In test/dev with missing token, logs the reply payload.
        """
        if isinstance(messages, dict):
            messages = [messages]

        if not self.channel_access_token:
            logger.info(
                "LINE_CHANNEL_ACCESS_TOKEN not set; mocking reply to %s: %s", reply_token, messages
            )
            return

        try:
            from linebot.v3.messaging import (
                ApiClient,
                Configuration,
                MessagingApi,
                ReplyMessageRequest,
            )

            config = Configuration(access_token=self.channel_access_token)
            with ApiClient(config) as api_client:
                messaging_api = MessagingApi(api_client)
                request = ReplyMessageRequest(
                    replyToken=reply_token,
                    messages=messages,
                )
                messaging_api.reply_message(request)
        except Exception as e:
            logger.error("Failed to send LINE reply message: %s", e)
            raise

    def push_message(
        self,
        to: str,
        messages: list[dict[str, Any]] | dict[str, Any],
    ) -> None:
        """
        Push a message to a specific LINE user ID.
        In production, calls LINE Messaging API.
        In test/dev with missing token, logs the message payload.
        """
        if isinstance(messages, dict):
            messages = [messages]

        if not self.channel_access_token:
            logger.info(
                "LINE_CHANNEL_ACCESS_TOKEN not set; mocking push to %s: %s", to, messages
            )
            return

        try:
            from linebot.v3.messaging import (
                ApiClient,
                Configuration,
                MessagingApi,
                PushMessageRequest,
            )

            config = Configuration(access_token=self.channel_access_token)
            with ApiClient(config) as api_client:
                messaging_api = MessagingApi(api_client)
                request = PushMessageRequest(
                    to=to,
                    messages=messages,
                )
                messaging_api.push_message(request)
        except Exception as e:
            logger.error("Failed to send LINE push message to %s: %s", to, e)
            raise

    def send_message(self, to: str, text: str) -> None:
        """Convenience method to push a simple text message to a user."""
        self.push_message(to=to, messages=[{"type": "text", "text": text}])

    def create_rich_menu(self, rich_menu_data: dict[str, Any]) -> str:
        """Create a new Rich Menu via LINE Messaging API."""
        if not self.channel_access_token:
            logger.info("LINE_CHANNEL_ACCESS_TOKEN not set; returning mock rich menu ID")
            return "mock-rich-menu-id"

        try:
            from linebot.v3.messaging import ApiClient, Configuration, MessagingApi

            config = Configuration(access_token=self.channel_access_token)
            with ApiClient(config) as api_client:
                messaging_api = MessagingApi(api_client)
                res = messaging_api.create_rich_menu(rich_menu_data)
                return res.rich_menu_id
        except Exception as e:
            logger.error("Failed to create LINE rich menu: %s", e)
            raise

    def link_rich_menu_to_user(self, user_id: str, rich_menu_id: str) -> None:
        """Link a Rich Menu to a specific LINE user."""
        if not self.channel_access_token:
            logger.info(
                "LINE_CHANNEL_ACCESS_TOKEN not set; mocking link %s -> %s", rich_menu_id, user_id
            )
            return

        try:
            from linebot.v3.messaging import ApiClient, Configuration, MessagingApi

            config = Configuration(access_token=self.channel_access_token)
            with ApiClient(config) as api_client:
                messaging_api = MessagingApi(api_client)
                messaging_api.link_rich_menu_id_to_user(user_id, rich_menu_id)
        except Exception as e:
            logger.error("Failed to link rich menu to user %s: %s", user_id, e)
            raise


line_client = LineClient()
