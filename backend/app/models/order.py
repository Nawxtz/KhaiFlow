from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class OrderStatus(StrEnum):
    """
    Order states for state machine across phases.
    From v1_buildable_spec.md §8:
    BROWSING -> ORDER_DRAFT -> ORDER_CONFIRMED -> ADDRESS_COLLECTION -> ADDRESS_CONFIRMED ->
    STOCK_RESERVED / AWAITING_PAYMENT -> PAYMENT_RECEIVED / RESERVATION_EXPIRED.
    """

    BROWSING = "BROWSING"
    ORDER_DRAFT = "ORDER_DRAFT"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    ADDRESS_COLLECTION = "ADDRESS_COLLECTION"
    ADDRESS_CONFIRMED = "ADDRESS_CONFIRMED"
    STOCK_RESERVED = "STOCK_RESERVED"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    RESERVATION_EXPIRED = "RESERVATION_EXPIRED"
    PAYMENT_RECONCILE = "PAYMENT_RECONCILE"
    FULFILLED = "FULFILLED"


class Order(Base):
    """
    Authoritative order table matching reference_schema.md:
    orders(id, line_user_id, status, total, currency, created_at, updated_at,
           ttl_expires_at, approval_state, payment_ref, risk_score) with shop_id.
    """

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    line_user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=OrderStatus.BROWSING.value, index=True
    )
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="THB")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    ttl_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_ref: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class OrderItem(Base):
    """
    Authoritative order items table matching reference_schema.md:
    order_items(id, order_id, sku, name, size, qty, unit_price, line_total) with shop_id.
    """

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
