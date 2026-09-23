from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserPrefs(Base):
    __tablename__ = "user_prefs"

    user_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    scope: Mapped[str] = mapped_column(String(20), primary_key=True, default="buyer")
    shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="th")
    theme: Mapped[str] = mapped_column(String(20), nullable=False, default="system")
    pdpa_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pdpa_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
