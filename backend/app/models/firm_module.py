"""Firm-module persistence (Phase 3 pilot hooks).

Tables are core-owned for the pilot so installs share one Postgres; payloads and
behaviour are driven by the firm package ``module/manifest.json``. Phase 5 may
move storage into firm-owned schema space.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FirmModuleCaseState(Base):
    """Per-matter state for a firm module (attrs, stages, checklist)."""

    __tablename__ = "firm_module_case_state"
    __table_args__ = (
        UniqueConstraint("module_id", "case_id", name="uq_firm_module_case_state_module_case"),
        Index("ix_firm_module_case_state_case_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id: Mapped[str] = mapped_column(String(80), nullable=False)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class FirmLifecycleOutbox(Base):
    """Transactional lifecycle notifications for firm modules (Phase 3/4 candidate)."""

    __tablename__ = "firm_lifecycle_outbox"
    __table_args__ = (Index("ix_firm_lifecycle_outbox_processed_at", "processed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
