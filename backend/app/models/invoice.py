"""SQLAlchemy models — invoice domain."""
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

class InvoiceSeq(Base):
    """Single-row sequence for global invoice numbers."""

    __tablename__ = "invoice_seq"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    next_num: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

class BillingSettings(Base):
    """Singleton row (id=1): default VAT % for new invoice lines."""

    __tablename__ = "billing_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    default_vat_percent: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, default=Decimal("20"))

class BillingLineTemplate(Base):
    """Admin-defined default fee / disbursement labels and amounts per matter sub-type."""

    __tablename__ = "billing_line_template"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_sub_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="CASCADE"), nullable=False
    )
    line_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # "fee" | "disbursement"
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    default_amount_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class CaseInvoice(Base):
    __tablename__ = "case_invoice"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    ledger_pair_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reversal_pair_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    total_pence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payee_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    credit_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class CaseInvoiceLine(Base):
    __tablename__ = "case_invoice_line"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_invoice.id", ondelete="CASCADE"), nullable=False
    )
    line_type: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount_pence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_pence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credit_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
