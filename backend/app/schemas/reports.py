from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class ReportFeeEarnerIdsIn(BaseModel):
    fee_earner_user_ids: list[uuid.UUID] = Field(min_length=1)

    model_config = {"extra": "forbid"}

class BillingReportIn(ReportFeeEarnerIdsIn):
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def _dates(self) -> BillingReportIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self

class WipReportIn(ReportFeeEarnerIdsIn):
    as_of: date | None = None

class TimeRecordedReportIn(ReportFeeEarnerIdsIn):
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def _dates(self) -> TimeRecordedReportIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self

class CasesReportIn(ReportFeeEarnerIdsIn):
    """Optional workflow status filter; omit or empty for all statuses."""

    statuses: list[str] | None = None

class CasesOpenedReportIn(ReportFeeEarnerIdsIn):
    date_from: date
    date_to: date
    include_quote: bool = True
    include_active: bool = True

    @model_validator(mode="after")
    def _dates(self) -> CasesOpenedReportIn:
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self

class EventsReportIn(ReportFeeEarnerIdsIn):
    date_from: date | None = None
    date_to: date | None = None
    template_ids: list[uuid.UUID] | None = None

    @model_validator(mode="after")
    def _dates(self) -> EventsReportIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self

class LedgerActivityReportIn(ReportFeeEarnerIdsIn):
    date_from: date | None = None
    date_to: date | None = None
    approved_only: bool = False

    @model_validator(mode="after")
    def _dates(self) -> LedgerActivityReportIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self

class AgedDebtReportIn(ReportFeeEarnerIdsIn):
    as_of: date | None = None

class ExceptionsReportIn(ReportFeeEarnerIdsIn):
    date_from: date | None = None
    date_to: date | None = None
    large_posting_min_pence: int = Field(default=500_000, ge=1)

    @model_validator(mode="after")
    def _dates(self) -> ExceptionsReportIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self

class ReconciliationPreviewOut(BaseModel):
    ledger_client_total_pence: int
    ledger_office_total_pence: int

class ClientAccountReconciliationOut(BaseModel):
    id: uuid.UUID
    period_end_date: date
    ledger_client_total_pence: int
    ledger_office_total_pence: int
    bank_statement_balance_pence: int
    difference_pence: int
    prepared_by_user_id: uuid.UUID
    prepared_by_name: str | None = None
    prepared_at: datetime
    approved_by_user_id: uuid.UUID | None = None
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    notes: str | None = None
    status: str

class ClientAccountReconciliationCreateIn(BaseModel):
    period_end_date: date
    bank_statement_balance_pence: int
    notes: str | None = Field(default=None, max_length=8000)

class ClientAccountReconciliationUpdateIn(BaseModel):
    bank_statement_balance_pence: int | None = None
    notes: str | None = Field(default=None, max_length=8000)
    refresh_ledger_totals: bool = True

class AccountantPackIn(ReportFeeEarnerIdsIn):
    period_end_date: date
    date_from: date | None = None
    date_to: date | None = None
    include_balances: bool = True
    include_billing: bool = True
    include_ledger_activity: bool = True
    include_aged_debt: bool = True
    include_exceptions: bool = False
    include_reconcile_doc: bool = True
    large_posting_min_pence: int = Field(default=500_000, ge=1)

    @model_validator(mode="after")
    def _dates(self) -> AccountantPackIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        if (self.date_from is None) != (self.date_to is None):
            raise ValueError("Provide both activity date_from and date_to, or leave both empty.")
        return self

class AccountantPackSectionOut(BaseModel):
    key: str
    label: str
    included: bool
    row_count: int | None = None
    note: str | None = None

class AccountantPackPreviewOut(BaseModel):
    period_end_date: date
    activity_date_from: date
    activity_date_to: date
    fee_earner_count: int
    reconcile_doc_available: bool
    sections: list[AccountantPackSectionOut]

class FeeEarnerPickOut(BaseModel):
    id: uuid.UUID
    display_name: str
    email: EmailStr

    model_config = {"from_attributes": True}
