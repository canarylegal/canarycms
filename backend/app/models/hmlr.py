"""SQLAlchemy models — HM Land Registry Business Gateway integration."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class HmlrIntegrationSettings(Base):
    """Singleton (id=1): Business Gateway credentials and mode."""

    __tablename__ = "hmlr_integration_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True = customer test / stub (bgtest). False = live Gateway.
    sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional Gateway customer id (not matter order reference).
    customer_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    post_anticipated_disbursement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # office | client
    anticipated_ledger_account: Mapped[str] = mapped_column(String(16), nullable=False, default="office")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class HmlrCaseLink(Base):
    """Per-matter Land Registry order reference (external reference for OC requests)."""

    __tablename__ = "hmlr_case_link"
    __table_args__ = (UniqueConstraint("case_id", name="uq_hmlr_case_link_case_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False
    )
    hmlr_reference: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class HmlrOrder(Base):
    """Official Copy (title known) request for a matter."""

    __tablename__ = "hmlr_order"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    title_number: Mapped[str] = mapped_column(String(32), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    want_register: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    want_title_plan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="Draft")
    gateway_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    poll_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fee_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    register_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    plan_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
