"""Pydantic schemas."""

from app.schemas.address_book import (
    AddressBookBase,
    AddressBookCreate,
    AddressBookDeleteResponse,
    AddressBookRead,
    AddressJsonModel,
)
from app.schemas.gateway_webhook import (
    GatewayWebhookPayload,
    GatewayWebhookResponse,
    WebhookResult,
)
from app.schemas.inventory import IngestSummary, InventoryItem
from app.schemas.order import (
    FulfillmentResult,
    LLMExtractedIntent,
    OrderBase,
    OrderCreate,
    OrderDraftIntent,
    OrderItemBase,
    OrderItemCreate,
    OrderItemRead,
    OrderRead,
    OrderSummaryResponse,
)
from app.schemas.payment import (
    GenerateQRRequest,
    PaymentQRPayloadSchema,
    PaymentTriggerRequest,
    PaymentTriggerResponse,
    ReservationSchema,
    VerifyQRRequest,
    VerifyQRResponse,
)
from app.schemas.verification import (
    ManualActionResponse,
    ManualApprovalRequest,
    ManualRejectRequest,
    SlipVerificationRequest,
    SlipVerificationResponse,
)

__all__ = [
    "AddressBookBase",
    "AddressBookCreate",
    "AddressBookDeleteResponse",
    "AddressBookRead",
    "AddressJsonModel",
    "FulfillmentResult",
    "GatewayWebhookPayload",
    "GatewayWebhookResponse",
    "GenerateQRRequest",
    "IngestSummary",
    "InventoryItem",
    "LLMExtractedIntent",
    "ManualActionResponse",
    "ManualApprovalRequest",
    "ManualRejectRequest",
    "OrderBase",
    "OrderCreate",
    "OrderDraftIntent",
    "OrderItemBase",
    "OrderItemCreate",
    "OrderItemRead",
    "OrderRead",
    "OrderSummaryResponse",
    "PaymentQRPayloadSchema",
    "PaymentTriggerRequest",
    "PaymentTriggerResponse",
    "ReservationSchema",
    "SlipVerificationRequest",
    "SlipVerificationResponse",
    "VerifyQRRequest",
    "VerifyQRResponse",
    "WebhookResult",
]
