from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InventorySheetSnapshot(Base):
    __tablename__ = "inventory_sheet_snapshot"

    sku: Mapped[str] = mapped_column(String(100), primary_key=True)
    field: Mapped[str] = mapped_column(String(50), primary_key=True)
    shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    last_value: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
