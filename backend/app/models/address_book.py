from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base


class AddressBook(Base):
    """
    Authoritative address_book table matching reference_schema.md:
    address_book(id, line_user_id, label, receiver_name, phone, address_json, is_default, created_at)
    with nullable, indexed shop_id.
    """

    __tablename__ = "address_book"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    line_user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    receiver_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    address_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
