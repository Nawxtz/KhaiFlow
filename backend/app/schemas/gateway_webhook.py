from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GatewayWebhookPayload(BaseModel):
    """
    Pydantic schema for parsing gateway/bank payment webhook JSON payloads.
    Option A confirmation per v1_buildable_spec.md §13, §20.
    """

    model_config = ConfigDict(extra="ignore")

    order_id: str = Field(..., description="Target order ID")
    amount: Decimal = Field(..., description="Payment amount in transaction currency")
    currency: str = Field(default="THB", description="3-letter currency code")
    event_key: str | None = Field(default=None, description="Unique event identifier from gateway")
    event_id: str | None = Field(default=None, description="Alternative event identifier field")
    status: str = Field(default="SUCCESS", description="Payment status reported by gateway")
    transaction_id: str | None = Field(default=None, description="Gateway transaction reference")
    payment_ref: str | None = Field(default=None, description="Payment reference")
    shop_id: str | None = Field(default=None, description="Shop identifier")
    channel: str = Field(default="gateway", description="Payment channel")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional gateway metadata")

    @model_validator(mode="after")
    def resolve_event_key(self) -> "GatewayWebhookPayload":
        """Ensure event_key is populated from event_key, event_id, transaction_id, or order_id."""
        if not self.event_key:
            if self.event_id:
                self.event_key = self.event_id
            elif self.transaction_id:
                self.event_key = f"gw_{self.transaction_id}"
            elif self.payment_ref:
                self.event_key = f"gw_{self.payment_ref}"
            elif self.order_id:
                self.event_key = f"evt_{self.order_id}"

        if not self.event_key or not self.event_key.strip():
            raise ValueError("Webhook payload must specify an event_key, event_id, or transaction_id.")

        self.event_key = self.event_key.strip()
        return self


@dataclass
class WebhookResult:
    """Internal service result for gateway webhook processing."""

    status: str
    success: bool
    is_duplicate: bool
    order_id: str | None
    event_key: str | None
    message: str
    order_status: str | None = None


class GatewayWebhookResponse(BaseModel):
    """HTTP response schema for POST /api/gateway/webhook."""

    status: str
    is_duplicate: bool
    order_id: str | None = None
    event_key: str | None = None
    order_status: str | None = None
    message: str
