from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PDPADeletion(Base):
    """
    Authoritative PDPA deletion audit log matching reference_schema.md:
    pdpa_deletions(id, line_user_id, requested_at, completed_at) with shop_id.
    """

    __tablename__ = "pdpa_deletions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    line_user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
