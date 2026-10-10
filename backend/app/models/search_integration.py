"""SQLAlchemy models — install-wide search provider selection."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SearchIntegrationSettings(Base):
    """Singleton (id=1): which search provider owns the matter Searches menu."""

    __tablename__ = "search_integration_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    # ``none`` | ``casera`` (extend as providers are added)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="none")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
