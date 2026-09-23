from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReservationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shop_id: str | None = None
    order_id: str
    sku: str
    qty: int
    state: str
    expires_at: datetime | None = None
    created_at: datetime


class PaymentQRPayloadSchema(BaseModel):
    order_id: str
    total: str
    currency: str = "THB"
    shop_account: str
    payload: str
    signature: str
    qr_data: str


class PaymentTriggerRequest(BaseModel):
    claim_key: str = Field(..., description="Unique claim or transaction reference key")
    order_id: str | None = Field(None, description="Associated order identifier")
    shop_id: str | None = Field(None, description="Shop identifier")
    channel: str = Field("webhook", description="Trigger source channel")
    payload: dict[str, Any] | None = Field(None, description="Raw trigger payload metadata")


class PaymentTriggerResponse(BaseModel):
    status: str
    is_duplicate: bool
    order_id: str | None = None
    claim_key: str
    message: str


class GenerateQRRequest(BaseModel):
    order_id: str
    total: Decimal
    currency: str = "THB"
    shop_account: str = "default_account"


class VerifyQRRequest(BaseModel):
    order_id: str
    total: Decimal
    currency: str = "THB"
    shop_account: str = "default_account"
    signature: str


class VerifyQRResponse(BaseModel):
    valid: bool
