from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PDPAConsentRequest(BaseModel):
    line_user_id: str
    consent: bool
    shop_id: str | None = None


class PDPAConsentResponse(BaseModel):
    line_user_id: str
    consent: bool
    consented_at: datetime | None = None
    status: str = "success"

    model_config = ConfigDict(from_attributes=True)


class PDPADeleteRequest(BaseModel):
    line_user_id: str
    shop_id: str | None = None


class PDPADeleteResponse(BaseModel):
    line_user_id: str
    anonymized_user_id: str
    addresses_deleted: int
    orders_anonymized: int
    status: str = "deleted"


class PDPARetentionJobResponse(BaseModel):
    deleted_user_ids: list[str]
    retention_months: int
    status: str = "completed"
