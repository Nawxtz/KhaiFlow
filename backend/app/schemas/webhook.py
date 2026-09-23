from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LineSource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = "user"
    user_id: str | None = Field(default=None, alias="userId")
    group_id: str | None = Field(default=None, alias="groupId")
    room_id: str | None = Field(default=None, alias="roomId")


class LineMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    type: str = "text"
    text: str | None = None


class LinePostback(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: str
    params: dict[str, Any] | None = None


class LineDeliveryContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    is_redelivery: bool = Field(default=False, alias="isRedelivery")


class LineWebhookEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    webhook_event_id: str = Field(..., alias="webhookEventId")
    type: str
    timestamp: int | None = None
    source: LineSource | None = None
    reply_token: str | None = Field(default=None, alias="replyToken")
    mode: str | None = None
    delivery_context: LineDeliveryContext | None = Field(default=None, alias="deliveryContext")
    message: LineMessage | None = None
    postback: LinePostback | None = None


class LineWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    destination: str | None = None
    events: list[LineWebhookEvent] = Field(default_factory=list)
