"""SQLAlchemy models — firm domain."""
from __future__ import annotations

import enum
import uuid
from decimal import Decimal
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    LargeBinary,
    Time,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

class LetterheadStyle(str, enum.Enum):
    """Letter compose: physical pre-printed stock vs digital header/footer template."""

    preprinted = "preprinted"
    digital = "digital"

class PrecedentKind(str, enum.Enum):
    letter = "letter"
    email = "email"
    document = "document"

class PrecedentCategory(Base):
    __tablename__ = "precedent_category"
    __table_args__ = (UniqueConstraint("matter_sub_type_id", "name", name="uq_precedent_category_sub_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_sub_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class FirmSettings(Base):
    """Singleton firm-wide configuration (id must always be 1)."""

    __tablename__ = "firm_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    trading_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    registered_company_name: Mapped[str | None] = mapped_column(String(400), nullable=True)
    addr_line1: Mapped[str | None] = mapped_column(String(300), nullable=True)
    addr_line2: Mapped[str | None] = mapped_column(String(300), nullable=True)
    town_city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    county: Mapped[str | None] = mapped_column(String(150), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    letterhead_style: Mapped[LetterheadStyle] = mapped_column(
        Enum(LetterheadStyle, name="letterhead_style"),
        nullable=False,
        default=LetterheadStyle.preprinted,
    )
    letterhead_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    quote_letterhead_style: Mapped[LetterheadStyle] = mapped_column(
        Enum(LetterheadStyle, name="letterhead_style"),
        nullable=False,
        default=LetterheadStyle.preprinted,
    )
    quote_letterhead_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    portal_logo_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    # Client portal page background only (#RRGGBB). Null = product default chrome.
    portal_background_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    default_signature_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    default_signature_scale: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    invoice_template_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    mandate_two_factor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mandate_password_rotation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_rotation_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    client_bank_account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    client_bank_sort_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    client_bank_account_number_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    client_bank_account_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class ReconciliationStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"

class ClientAccountReconciliation(Base):
    """Month-end client account reconciliation snapshot (one row per period end date)."""

    __tablename__ = "client_account_reconciliation"
    __table_args__ = (UniqueConstraint("period_end_date", name="uq_client_account_reconciliation_period_end"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    ledger_client_total_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    ledger_office_total_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    bank_statement_balance_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    difference_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    prepared_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus, name="reconciliation_status"),
        nullable=False,
        default=ReconciliationStatus.draft,
    )

class MergeCodeCatalog(Base):
    """Editable descriptions for precedent merge tokens; keys mirror ``docx_util.PRECEDENT_CODES``."""

    __tablename__ = "merge_code_catalog"

    code: Mapped[str] = mapped_column(String(160), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Precedent(Base):
    __tablename__ = "precedent"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    reference: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[PrecedentKind] = mapped_column(Enum(PrecedentKind, name="precedent_kind"), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("file.id", ondelete="CASCADE"), nullable=False)
    # Scope: (NULL,NULL,NULL) = all cases; (H,NULL,NULL) = all sub-types under head H; (H,S,NULL) = all categories under sub S; (H,S,C) = one category.
    matter_head_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_head_type.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    matter_sub_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("precedent_category.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class EmailIntegrationSettings(Base):
    """Singleton row (id=1): mailto vs Microsoft Graph; optional Entra app credentials (secret encrypted)."""

    __tablename__ = "email_integration_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    integration_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="microsoft_graph")
    graph_tenant_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph_client_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph_client_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    outlook_web_mail_base: Mapped[str | None] = mapped_column(Text, nullable=True)
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alert_transport: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")
    graph_send_mailbox: Mapped[str | None] = mapped_column(String(320), nullable=True)
    graph_send_from_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class SmtpNotificationSettings(Base):
    """Singleton (id=1): outbound SMTP for calendar (and future) e-mail alerts."""

    __tablename__ = "smtp_notification_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    host: Mapped[str | None] = mapped_column(String(300), nullable=True)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    username: Mapped[str | None] = mapped_column(String(320), nullable=True)
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
