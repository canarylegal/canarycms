"""SQLAlchemy models — firm bank accounts, statement lines, recon, EOM, Xero."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FirmBankAccount(Base):
    __tablename__ = "firm_bank_account"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="client")  # client|office
    sort_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    account_number_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class BankStatementImport(Base):
    __tablename__ = "bank_statement_import"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_bank_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm_bank_account.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    imported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BankStatementLine(Base):
    __tablename__ = "bank_statement_line"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_statement_import.id", ondelete="CASCADE"), nullable=False
    )
    firm_bank_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm_bank_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    statement_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Signed: positive = money in (receipt), negative = money out (payment).
    amount_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    balance_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_pair_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    matched_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class BankReconciliation(Base):
    __tablename__ = "bank_reconciliation"
    __table_args__ = (
        UniqueConstraint("firm_bank_account_id", "period_end_date", name="uq_bank_reconciliation_account_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_bank_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm_bank_account.id", ondelete="CASCADE"), nullable=False
    )
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    statement_balance_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    ledger_total_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unpresented_total_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmatched_statement_total_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    difference_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    prepared_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClientAccountEom(Base):
    __tablename__ = "client_account_eom"
    __table_args__ = (
        UniqueConstraint("firm_bank_account_id", "period_end_date", name="uq_client_account_eom_account_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_bank_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm_bank_account.id", ondelete="CASCADE"), nullable=False
    )
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="application/zip")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CaseInvoiceAllocation(Base):
    __tablename__ = "case_invoice_allocation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_invoice.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ledger_pair_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    amount_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class InterMatterJournal(Base):
    __tablename__ = "inter_matter_journal"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False
    )
    to_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False
    )
    firm_bank_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm_bank_account.id", ondelete="SET NULL"), nullable=True
    )
    amount_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    from_pair_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    to_pair_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class XeroIntegrationSettings(Base):
    __tablename__ = "xero_integration_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tenant_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    office_income_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    office_bank_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vat_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disbursement_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class XeroJournalExport(Base):
    __tablename__ = "xero_journal_export"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="text/csv")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
