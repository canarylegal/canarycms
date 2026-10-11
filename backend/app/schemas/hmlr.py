"""Pydantic schemas for HM Land Registry integration."""

from __future__ import annotations

import uuid
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field


class HmlrIntegrationSettingsOut(BaseModel):
    enabled: bool
    sandbox: bool
    username: str | None = None
    password_configured: bool = False
    customer_reference: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    post_anticipated_disbursement: bool = False
    anticipated_ledger_account: Literal["office", "client"] = "office"
    configured: bool = False
    # True until a Gateway client certificate is installed / live calls are possible.
    mock_mode: bool = True


class HmlrIntegrationSettingsUpdate(BaseModel):
    enabled: bool | None = None
    sandbox: bool | None = None
    username: str | None = None
    password: str | None = None
    customer_reference: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    post_anticipated_disbursement: bool | None = None
    anticipated_ledger_account: Literal["office", "client"] | None = None


class HmlrOrderOut(BaseModel):
    id: uuid.UUID
    product: str = "official_copies"
    title_number: str
    external_reference: str
    want_register: bool
    want_title_plan: bool
    state: str
    fee_pence: int
    error_message: str | None = None
    register_file_id: uuid.UUID | None = None
    plan_file_id: uuid.UUID | None = None
    sandbox: bool
    placed_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


HmlrServiceProduct = Literal["priority", "full", "bankruptcy", "registration"]


class HmlrServiceOrderIn(BaseModel):
    """Place a non–official-copy Land Registry product (design preview / Gateway later)."""

    product: HmlrServiceProduct
    title_or_party: str = Field(min_length=1, max_length=256)
    reference: str | None = Field(default=None, max_length=128)
    fee_pence: int = Field(ge=0, le=50_000_000)
    override_funds_warning: bool = False


class HmlrRailStatusItem(BaseModel):
    """Compact matter-rail status line (label + tone only)."""

    id: str
    label: str
    tone: Literal["ok", "warn", "bad", "neutral"] = "neutral"


class HmlrSummaryOut(BaseModel):
    configured: bool
    enabled: bool
    sandbox: bool
    mock_mode: bool
    orders: list[HmlrOrderOut] = Field(default_factory=list)
    suggested_title_numbers: list[str] = Field(default_factory=list)
    suggested_reference: str = ""
    hmlr_reference: str | None = None
    rail_items: list[HmlrRailStatusItem] = Field(default_factory=list)


class HmlrCreateOrderIn(BaseModel):
    title_number: str = Field(min_length=1, max_length=32)
    want_register: bool = True
    want_title_plan: bool = True
    # Matter-level reference (stored on first use); ignored once the matter link exists.
    reference: str | None = Field(default=None, max_length=128)
    external_reference: str | None = Field(default=None, max_length=128)
    override_funds_warning: bool = False


class HmlrAddressSearchIn(BaseModel):
    """Address search for official copies (Gateway title enquiry — mock until SOAP wired)."""

    title_number: str | None = Field(default=None, max_length=32)
    flat: str | None = Field(default=None, max_length=128)
    house: str | None = Field(default=None, max_length=128)
    street: str | None = Field(default=None, max_length=256)
    town: str | None = Field(default=None, max_length=128)
    postcode: str | None = Field(default=None, max_length=32)


class HmlrTitleMatchOut(BaseModel):
    title_number: str
    address: str
    tenure: str | None = None


class HmlrAddressSearchOut(BaseModel):
    matches: list[HmlrTitleMatchOut] = Field(default_factory=list)
    mock: bool = True


class HmlrDocumentOptionOut(BaseModel):
    code: str
    label: str
    fee_pence: int
    description: str | None = None


class HmlrTitleDocumentsOut(BaseModel):
    title_number: str
    address: str | None = None
    documents: list[HmlrDocumentOptionOut] = Field(default_factory=list)
    mock: bool = True


class HmlrBatchOrderLineIn(BaseModel):
    title_number: str = Field(min_length=1, max_length=32)
    document_codes: list[str] = Field(default_factory=list)


class HmlrBatchOrderIn(BaseModel):
    lines: list[HmlrBatchOrderLineIn] = Field(min_length=1)
    reference: str | None = Field(default=None, max_length=128)
    override_funds_warning: bool = False


class HmlrBatchOrderOut(BaseModel):
    orders: list[HmlrOrderOut] = Field(default_factory=list)
    total_fee_pence: int = 0


class HmlrProprietorCheckIn(BaseModel):
    """Priority-search name match against the register (mock until Gateway wired)."""

    title_number: str = Field(min_length=1, max_length=32)
    proprietor_name: str = Field(min_length=1, max_length=512)


class HmlrProprietorCheckOut(BaseModel):
    matched: bool
    title_number: str
    # Present in sandbox mock so fee-earners can complete demos; omitted on live Gateway.
    sandbox_hint: str | None = None
    message: str | None = None
    mock: bool = True
