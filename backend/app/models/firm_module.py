"""Firm-module persistence (Phase 5).

``FirmModuleCaseState`` lives in the firm Postgres schema (default shape: same
cluster, firm-owned schema). ``FirmLifecycleOutbox`` stays in core — it is the
platform lifecycle notification queue, not firm business data.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Pilot firm schema (must match example-firm-pilot manifest storage.schema).
FIRM_EXAMPLE_PILOT_SCHEMA = "firm_example_pilot"


class FirmModuleCaseState(Base):
    """Per-matter firm workflow state (stage, checklist, attrs). Firm-owned schema."""

    __tablename__ = "case_state"
    __table_args__ = (
        UniqueConstraint("module_id", "case_id", name="uq_firm_example_pilot_case_state_module_case"),
        Index("ix_firm_example_pilot_case_state_case_id", "case_id"),
        {"schema": FIRM_EXAMPLE_PILOT_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id: Mapped[str] = mapped_column(String(80), nullable=False)
    # Stable core ID reference only — no FK into public.case (firm-owned boundary).
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class FirmLifecycleOutbox(Base):
    """Core lifecycle notification queue for firm modules (stays in public schema)."""

    __tablename__ = "firm_lifecycle_outbox"
    __table_args__ = (Index("ix_firm_lifecycle_outbox_processed_at", "processed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
