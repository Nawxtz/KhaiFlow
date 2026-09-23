from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AddressJsonModel(BaseModel):
    """Structured address components per v1_buildable_spec.md §20 / §10."""

    receiver_name: str
    phone: str
    house_number: str | None = None
    street: str
    subdistrict: str
    district: str
    province: str
    postcode: str
    full_address: str


class AddressBookBase(BaseModel):
    shop_id: str | None = None
    line_user_id: str
    label: str | None = None
    receiver_name: str
    phone: str
    address_json: dict[str, Any]
    is_default: bool = False


class AddressBookCreate(AddressBookBase):
    pass


class AddressBookRead(AddressBookBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AddressBookDeleteResponse(BaseModel):
    status: str = "deleted"
    id: int
