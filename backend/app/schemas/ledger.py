from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class LedgerPermissionsOut(BaseModel):
    can_approve_ledger: bool
    can_approve_invoices: bool = False
    accounts_workspace_access: bool = False
    can_post_client: bool = False
    can_post_office: bool = False
    can_post_anticipated: bool = False

class LedgerPostCreate(BaseModel):
    """
    Body for POST /cases/{id}/ledger/post.

    A single posting records one transaction that affects one or both accounts.
    SAR-typical use cases:
      - client receipt  : debit client, credit client  (money in to client account)
      - bill payment    : debit client, credit office   (transfer to office on bill)
      - office disbursement: debit office, credit office (e.g. search fee)
    """

    description: str = Field(min_length=1, max_length=500)
    reference: str | None = Field(default=None, max_length=200)
    contact_label: str | None = Field(default=None, max_length=300)
    case_contact_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    amount_pence: int = Field(gt=0, description="Amount in pence (integer)")
    # Which account(s) to affect and in which direction.
    # At least one leg is required; both may be supplied.
    client_direction: Literal["debit", "credit"] | None = None
    office_direction: Literal["debit", "credit"] | None = None
    anticipated: bool = False
    anticipated_for_date: date | None = None

    @model_validator(mode="after")
    def anticipated_date_required(self) -> LedgerPostCreate:
        if self.anticipated and self.anticipated_for_date is None:
            raise ValueError("anticipated_for_date is required when anticipated is true")
        return self

    model_config = {"extra": "forbid"}

class LedgerPairUpdate(BaseModel):
    """Edit an unapproved or anticipated posting before approval."""

    amount_pence: int | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, min_length=1, max_length=500)
    reference: str | None = Field(default=None, max_length=200)
    anticipated_for_date: date | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def at_least_one_field(self) -> LedgerPairUpdate:
        if (
            self.amount_pence is None
            and self.description is None
            and self.reference is None
            and self.anticipated_for_date is None
        ):
            raise ValueError("At least one field is required.")
        return self

class RejectCommentIn(BaseModel):
    """Optional comment when rejecting an anticipated payment or pending invoice."""

    comment: str | None = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}

class LedgerEntryOut(BaseModel):
    id: uuid.UUID
    pair_id: uuid.UUID
    account_type: Literal["client", "office"]
    direction: Literal["debit", "credit"]
    amount_pence: int
    description: str
    reference: str | None
    contact_label: str | None = None
    case_contact_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    posted_by_user_id: uuid.UUID | None
    posted_at: datetime
    is_approved: bool
    is_anticipated: bool = False
    anticipated_for_date: date | None = None

    model_config = {"from_attributes": True}

class LedgerAccountSummary(BaseModel):
    account_type: Literal["client", "office"]
    balance_pence: int  # positive = net credit; negative = net debit

class LedgerOut(BaseModel):
    entries: list[LedgerEntryOut]
    client: LedgerAccountSummary
    office: LedgerAccountSummary

class CaseInvoiceLineCreate(BaseModel):
    line_type: Literal["fee", "disbursement", "vat"]
    description: str = Field(min_length=1, max_length=500)
    amount_pence: int = Field(gt=0)
    tax_pence: int = Field(default=0, ge=0)
    credit_user_id: uuid.UUID | None = None

class CaseInvoiceCreate(BaseModel):
    credit_user_id: uuid.UUID
    payee_name: str | None = Field(default=None, max_length=500)
    contact_id: uuid.UUID | None = None
    lines: list[CaseInvoiceLineCreate] = Field(default_factory=list)
    time_entry_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_lines_or_time(self) -> CaseInvoiceCreate:
        if not self.lines and not self.time_entry_ids:
            raise ValueError("At least one invoice line or time entry is required.")
        return self

    model_config = {"extra": "forbid"}

class CaseInvoiceLineOut(BaseModel):
    id: uuid.UUID
    line_type: str
    description: str
    amount_pence: int
    tax_pence: int
    credit_user_id: uuid.UUID | None

class CaseInvoiceOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    invoice_number: str
    status: str
    total_pence: int
    payee_name: str | None
    credit_user_id: uuid.UUID | None = None
    credit_user_display_name: str | None = None
    contact_id: uuid.UUID | None
    ledger_pair_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    voided_at: datetime | None
    created_at: datetime
    document_file_id: uuid.UUID | None = None
    lines: list[CaseInvoiceLineOut]

class CaseInvoicesOut(BaseModel):
    case_id: uuid.UUID
    invoices: list[CaseInvoiceOut]

class BillingSettingsOut(BaseModel):
    default_vat_percent: float

class BillingSettingsUpdate(BaseModel):
    default_vat_percent: float = Field(ge=0, le=100)

    model_config = {"extra": "forbid"}

class BillingLineTemplateOut(BaseModel):
    id: uuid.UUID
    matter_sub_type_id: uuid.UUID
    line_kind: Literal["fee", "disbursement"]
    label: str
    default_amount_pence: int
    sort_order: int

class BillingLineTemplateCreate(BaseModel):
    matter_sub_type_id: uuid.UUID
    line_kind: Literal["fee", "disbursement"]
    label: str = Field(min_length=1, max_length=200)
    default_amount_pence: int = Field(default=0, ge=0)
    sort_order: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}

class BillingLineTemplateUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    default_amount_pence: int | None = Field(default=None, ge=0)
    sort_order: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}

class InvoiceBillingDefaultsUser(BaseModel):
    id: str
    email: str
    display_name: str

class InvoiceBillingDefaultsOut(BaseModel):
    default_vat_percent: float
    fee_earner_user_id: uuid.UUID | None = None
    fee_templates: list[BillingLineTemplateOut]
    disbursement_templates: list[BillingLineTemplateOut]
    users: list[InvoiceBillingDefaultsUser]
