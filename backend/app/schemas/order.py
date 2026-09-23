from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import OrderStatus


class OrderItemBase(BaseModel):
    sku: str
    name: str
    size: str | None = None
    qty: int = Field(default=1, ge=1)
    unit_price: Decimal
    line_total: Decimal


class OrderItemCreate(BaseModel):
    sku: str
    name: str | None = None
    size: str | None = None
    qty: int = Field(default=1, ge=1)
    unit_price: Decimal | None = None


class OrderItemRead(OrderItemBase):
    id: int
    order_id: str
    shop_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class OrderBase(BaseModel):
    shop_id: str | None = None
    line_user_id: str
    status: OrderStatus = OrderStatus.BROWSING
    currency: str = "THB"


class OrderCreate(BaseModel):
    shop_id: str | None = None
    line_user_id: str
    items: list[OrderItemCreate] = []


class OrderRead(BaseModel):
    id: str
    shop_id: str | None = None
    line_user_id: str
    status: str
    total: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime
    ttl_expires_at: datetime | None = None
    approval_state: str | None = None
    payment_ref: str | None = None
    risk_score: int | None = None
    items: list[OrderItemRead] = []

    model_config = ConfigDict(from_attributes=True)


class OrderSummaryResponse(BaseModel):
    order_id: str
    status: str
    total: Decimal
    currency: str
    items_count: int
    items: list[OrderItemRead]

    model_config = ConfigDict(from_attributes=True)


class LLMExtractedIntent(BaseModel):
    """
    Extracted order intent from LLM output.
    extra='forbid' ensures any prompt-injection fields (e.g. unit_price, status) are rejected.
    """

    sku: str | None = None
    name: str | None = None
    qty: int = Field(default=1, ge=1)
    size: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class OrderDraftIntent(BaseModel):
    """
    Normalized order draft intent matching the shape of guided order item.
    unit_price and line_total are strictly sourced from database inventory.
    """

    sku: str
    name: str
    qty: int = Field(default=1, ge=1)
    size: str | None = None
    unit_price: Decimal
    line_total: Decimal

    model_config = ConfigDict(extra="forbid")


class FulfillmentResult(BaseModel):
    success: bool
    order_id: str
    status: str
    rows_written: int = 0
    already_fulfilled: bool = False
    message: str

    model_config = ConfigDict(from_attributes=True)
