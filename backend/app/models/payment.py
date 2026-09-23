from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConsumedPaymentClaim(Base):
    """
    Authoritative consumed payment claims table matching reference_schema.md:
    consumed_payment_claims(id, claim_key UNIQUE, claim_type[ref|img], order_id,
                            state[PENDING|CONFIRMED|RELEASED], consumed_at) with shop_id.
    Used for cross-order fraud deduplication and trigger idempotency.
    """

    __tablename__ = "consumed_payment_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    claim_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    claim_type: Mapped[str | None] = mapped_column(String(50), nullable=True, default="ref")
    order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True, default="CONFIRMED")
    consumed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PaymentEvent(Base):
    """
    Authoritative payment events table matching reference_schema.md:
    payment_events(id, event_key UNIQUE, order_id, channel, payload_hash, decision, created_at) with shop_id.
    Includes event_type, payload_json, received_at for audit trail and idempotency.
    """

    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    event_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Reservation(Base):
    """
    Authoritative stock reservations table matching reference_schema.md:
    reservations(id, order_id, sku, qty, state[RESERVED|CONFIRMED|RELEASED], expires_at) with shop_id.
    """

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    order_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(
        String(50), nullable=False, default="RESERVED", index=True
    )  # RESERVED | CONFIRMED | RELEASED
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
