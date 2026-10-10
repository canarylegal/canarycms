"""Pydantic schemas — firm bank accounts, statement recon, EOM, Xero, journals."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

PaymentMethod = Literal[
    "faster_payments",
    "bacs",
    "chaps",
    "cheque",
    "card",
    "journal",
    "other",
]
BankAccountKind = Literal["client", "office"]


class FirmBankAccountOut(BaseModel):
    id: uuid.UUID
    name: str
    account_kind: BankAccountKind
    sort_code: str | None = None
    account_number: str | None = None
    account_number_last4: str | None = None
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime


class FirmBankAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    account_kind: BankAccountKind = "client"
    sort_code: str | None = Field(default=None, max_length=16)
    account_number: str | None = Field(default=None, max_length=32)
    is_default: bool = False
    is_active: bool = True

    model_config = {"extra": "forbid"}


class FirmBankAccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_code: str | None = Field(default=None, max_length=16)
    account_number: str | None = Field(default=None, max_length=32)
    is_default: bool | None = None
    is_active: bool | None = None

    model_config = {"extra": "forbid"}


class BankStatementLineOut(BaseModel):
    id: uuid.UUID
    import_id: uuid.UUID
    firm_bank_account_id: uuid.UUID
    statement_date: date
    amount_pence: int
    description: str
    reference: str | None = None
    balance_pence: int | None = None
    matched_pair_id: uuid.UUID | None = None
    matched_at: datetime | None = None
    ignored: bool = False


class BankStatementImportOut(BaseModel):
    id: uuid.UUID
    firm_bank_account_id: uuid.UUID
    filename: str | None = None
    imported_at: datetime
    line_count: int
    lines: list[BankStatementLineOut] = Field(default_factory=list)


class BankStatementMatchIn(BaseModel):
    ledger_pair_id: uuid.UUID

    model_config = {"extra": "forbid"}


class UnpresentedLedgerLegOut(BaseModel):
    pair_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str | None = None
    posted_at: datetime
    amount_pence: int
    direction: Literal["debit", "credit"]
    description: str
    reference: str | None = None
    payment_method: str | None = None


class BankReconciliationOut(BaseModel):
    id: uuid.UUID
    firm_bank_account_id: uuid.UUID
    period_end_date: date
    statement_balance_pence: int
    ledger_total_pence: int
    unpresented_total_pence: int
    unmatched_statement_total_pence: int
    difference_pence: int
    status: str
    notes: str | None = None
    prepared_at: datetime
    approved_at: datetime | None = None


class BankReconciliationCreate(BaseModel):
    firm_bank_account_id: uuid.UUID
    period_end_date: date
    statement_balance_pence: int
    notes: str | None = Field(default=None, max_length=4000)

    model_config = {"extra": "forbid"}


class BankReconciliationUpdate(BaseModel):
    statement_balance_pence: int | None = None
    notes: str | None = Field(default=None, max_length=4000)

    model_config = {"extra": "forbid"}


class ClientAccountEomOut(BaseModel):
    id: uuid.UUID
    firm_bank_account_id: uuid.UUID
    period_end_date: date
    generated_at: datetime
    filename: str
    notes: str | None = None


class ClientAccountEomCreate(BaseModel):
    firm_bank_account_id: uuid.UUID
    period_end_date: date
    notes: str | None = Field(default=None, max_length=4000)

    model_config = {"extra": "forbid"}


class InvoiceAllocationIn(BaseModel):
    ledger_pair_id: uuid.UUID
    amount_pence: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


class InvoiceAllocationOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    ledger_pair_id: uuid.UUID
    amount_pence: int
    allocated_at: datetime
    notes: str | None = None


class InterMatterJournalCreate(BaseModel):
    from_case_id: uuid.UUID
    to_case_id: uuid.UUID
    amount_pence: int = Field(gt=0)
    description: str = Field(min_length=1, max_length=500)
    firm_bank_account_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=200)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def distinct_matters(self) -> InterMatterJournalCreate:
        if self.from_case_id == self.to_case_id:
            raise ValueError("from_case_id and to_case_id must differ")
        return self


class InterMatterJournalOut(BaseModel):
    id: uuid.UUID
    from_case_id: uuid.UUID
    to_case_id: uuid.UUID
    firm_bank_account_id: uuid.UUID | None = None
    amount_pence: int
    description: str
    from_pair_id: uuid.UUID
    to_pair_id: uuid.UUID
    created_at: datetime


class FinanceLedgerBridgeIn(BaseModel):
    """Post selected Finance worksheet debit lines as anticipated office (or client) disbursements."""

    item_ids: list[uuid.UUID] = Field(min_length=1)
    ledger_account: Literal["office", "client"] = "office"
    anticipated: bool = True
    anticipated_for_date: date | None = None
    firm_bank_account_id: uuid.UUID | None = None
    payment_method: PaymentMethod | None = None

    model_config = {"extra": "forbid"}


class FinanceLedgerBridgeOut(BaseModel):
    posted_count: int
    pair_ids: list[uuid.UUID]


class XeroSettingsOut(BaseModel):
    enabled: bool
    tenant_name: str | None = None
    office_income_code: str | None = None
    office_bank_code: str | None = None
    vat_code: str | None = None
    disbursement_code: str | None = None


class XeroSettingsUpdate(BaseModel):
    enabled: bool | None = None
    tenant_name: str | None = Field(default=None, max_length=200)
    office_income_code: str | None = Field(default=None, max_length=64)
    office_bank_code: str | None = Field(default=None, max_length=64)
    vat_code: str | None = Field(default=None, max_length=64)
    disbursement_code: str | None = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}


class XeroExportCreate(BaseModel):
    period_from: date
    period_to: date

    model_config = {"extra": "forbid"}


class XeroExportOut(BaseModel):
    id: uuid.UUID
    period_from: date
    period_to: date
    generated_at: datetime
    filename: str
    row_count: int
