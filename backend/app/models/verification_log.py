from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VerificationLog(Base):
    """
    Authoritative verification logs table matching reference_schema.md:
    verification_logs(id, order_id, channel, checks_json, risk_score, decision, created_at)
    with nullable indexed shop_id, and slip_hash / result fields per Phase 7 spec.
    """

    __tablename__ = "verification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    slip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True, default="slip")
    checks_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
