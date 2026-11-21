"""Append-only evidence of explicitly approved operator corrections."""

import uuid
from datetime import datetime
from sqlalchemy import DateTime, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.timeutil import utcnow


class CanarySignRecovery(Base):
    __tablename__ = "canary_sign_recovery"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    record: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
