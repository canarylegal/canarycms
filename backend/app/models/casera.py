"""SQLAlchemy models — Casera searches integration."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CaseraIntegrationSettings(Base):
    """Singleton (id=1): Casera API credentials and webhook config."""

    __tablename__ = "casera_integration_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    client_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_path_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_base_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_anticipated_disbursement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # office | client — which ledger anticipated search costs debit.
    anticipated_ledger_account: Mapped[str] = mapped_column(String(16), nullable=False, default="office")
    add_to_completion_statement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_on_result_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CaseraCaseLink(Base):
    """One Casera case per Canary matter."""

    __tablename__ = "casera_case_link"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_casera_case_link_case_id"),
        UniqueConstraint("casera_case_id", name="uq_casera_case_link_casera_case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    casera_case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    casera_reference: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CaseraOrder(Base):
    __tablename__ = "casera_order"
    __table_args__ = (UniqueConstraint("casera_order_id", name="uq_casera_order_casera_order_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    casera_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    casera_case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="Conveyancing")
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="Draft")
    total_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    selected_product_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    selected_pack_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CaseraOrderProduct(Base):
    __tablename__ = "casera_order_product"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("casera_order.id", ondelete="CASCADE"), nullable=False
    )
    casera_product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    casera_order_product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="Idle")
    price_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True)
    file_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    result_landed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CaseraWebhookEvent(Base):
    __tablename__ = "casera_webhook_event"
    __table_args__ = (UniqueConstraint("event_key", name="uq_casera_webhook_event_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_key: Mapped[str] = mapped_column(String(256), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
