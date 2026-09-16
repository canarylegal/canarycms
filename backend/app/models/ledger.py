"""SQLAlchemy models — ledger domain."""
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

class LedgerAccountType(str, enum.Enum):
    client = "client"
    office = "office"

class LedgerDirection(str, enum.Enum):
    debit = "debit"
    credit = "credit"

class LedgerAccount(Base):
    """One client account + one office account per case, created on first access."""

    __tablename__ = "ledger_account"
    __table_args__ = (UniqueConstraint("case_id", "account_type", name="uq_ledger_account_case_type"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False
    )
    account_type: Mapped[LedgerAccountType] = mapped_column(
        Enum(LedgerAccountType, name="ledger_account_type"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class LedgerEntry(Base):
    """Single leg of a double-entry posting; two rows share the same pair_id."""

    __tablename__ = "ledger_entry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_account.id", ondelete="CASCADE"), nullable=False
    )
    pair_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    direction: Mapped[LedgerDirection] = mapped_column(
        Enum(LedgerDirection, name="ledger_direction"), nullable=False
    )
    # Stored in integer pence to avoid floating-point errors.
    amount_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    case_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_contact.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL"), nullable=True, index=True
    )
    posted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_anticipated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    anticipated_for_date: Mapped[date | None] = mapped_column(Date, nullable=True)
