"""SQLAlchemy models — commercial funds policy (global shortfall behaviour)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CommercialFundsSettings(Base):
    """Singleton (id=1): shortfall policy for commercial connector orders."""

    __tablename__ = "commercial_funds_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    # reject | warn_override
    shortfall_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="warn_override")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
