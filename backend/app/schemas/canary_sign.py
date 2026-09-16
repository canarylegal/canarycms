from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.portal import PortalGrantSummaryOut


class CanarySignStaffOptionsOut(BaseModel):
    enabled: bool = True

class CanarySignSendRecipientIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    email: EmailStr
    routing_order: int = Field(default=1, ge=1, le=99)
    case_contact_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None

class CanarySignFieldSpecIn(BaseModel):
    field_type: Literal["signature", "initials", "date", "printed_name", "checkbox"]
    recipient_id: uuid.UUID | None = None
    routing_order: int | None = Field(default=None, ge=1, le=99)
    label: str | None = Field(default=None, max_length=200)
    required: bool = True
    sort_order: int = 0
    placement_mode: Literal["fixed"] = "fixed"
    page: int = Field(ge=1, le=9999)
    x_pct: float = Field(ge=0, le=100)
    y_pct: float = Field(ge=0, le=100)
    w_pct: float = Field(ge=0, le=100)
    h_pct: float = Field(ge=0, le=100)

class CanarySignSendIn(BaseModel):
    source_file_id: uuid.UUID
    subject: str | None = Field(default=None, max_length=500)
    order_mode: Literal["parallel", "sequential"] = "parallel"
    expires_in_days: int = Field(default=14, ge=1, le=365)
    recipients: list[CanarySignSendRecipientIn] = Field(min_length=1, max_length=20)
    fields: list[CanarySignFieldSpecIn] = Field(min_length=1, max_length=200)
    # Required when the source PDF has AcroForm fields: True keeps them, False strips them.
    retain_fillable_form: bool | None = None

class CanarySignVoidIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

class CanarySignFieldOut(BaseModel):
    id: uuid.UUID
    recipient_id: uuid.UUID
    field_type: str
    label: str | None = None
    required: bool = True
    sort_order: int = 0
    placement_mode: str = "free"
    page: int | None = None
    x_pct: float | None = None
    y_pct: float | None = None
    w_pct: float | None = None
    h_pct: float | None = None
    value: dict | None = None
    filled_at: datetime | None = None

class CanarySignRecipientOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    routing_order: int
    status: str
    decline_reason: str | None = None
    signed_at: datetime | None = None
    viewed_at: datetime | None = None
    contact_id: uuid.UUID | None = None
    case_contact_id: uuid.UUID | None = None

class CanarySignSigningRequestOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    source_file_id: uuid.UUID
    source_filename: str = ""
    snapshot_pdf_file_id: uuid.UUID | None = None
    signed_file_id: uuid.UUID | None = None
    certificate_file_id: uuid.UUID | None = None
    subject: str
    status: str
    status_detail: str | None = None
    order_mode: str
    expires_at: datetime | None = None
    completed_at: datetime | None = None
    voided_at: datetime | None = None
    created_at: datetime | None = None
    has_fillable_form: bool = False
    form_locked_by_recipient_id: uuid.UUID | None = None
    form_completed_at: datetime | None = None
    recipients: list[CanarySignRecipientOut] = []
    fields: list[CanarySignFieldOut] = []

class CanarySignMenuRowOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    case_number: str | None = None
    client_name: str | None = None
    matter_description: str = ""
    subject: str
    source_filename: str = ""
    status: str
    status_detail: str | None = None
    order_mode: str = "parallel"
    sent_by_display_name: str | None = None
    recipients_summary: str = ""
    expires_at: datetime | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    voided_at: datetime | None = None

class CanarySignAcroFormFieldOut(BaseModel):
    name: str
    label: str = ""
    field_type: str = "text"
    required: bool = False
    page: int = 1
    x_pct: float = 0
    y_pct: float = 0
    w_pct: float = 10
    h_pct: float = 4
    options: list[str] = []
    current_value: str = ""
    multiline: bool = False

class PortalCanarySignOut(BaseModel):
    id: uuid.UUID
    subject: str
    status: str
    status_detail: str | None = None
    order_mode: str = "parallel"
    expires_at: datetime | None = None
    can_sign: bool
    recipient_id: uuid.UUID
    recipient_name: str = ""
    recipient_status: str = "pending"
    sign_token: str
    matter_label: str = ""
    case_id: uuid.UUID | None = None
    fields: list[CanarySignFieldOut] = []
    disclaimer: str = ""
    has_fillable_form: bool = False
    form_fields: list[CanarySignAcroFormFieldOut] = []
    form_responses: dict = Field(default_factory=dict)
    form_locked: bool = False
    form_locked_by_recipient_id: uuid.UUID | None = None
    form_locked_by_name: str | None = None
    form_lock_held_by_me: bool = False
    form_completed: bool = False
    can_edit_form: bool = False
    can_claim_form_lock: bool = False

class PortalCanarySignExchangeIn(BaseModel):
    sign_token: str = Field(min_length=10, max_length=128)

class PortalCanarySignExchangeOut(BaseModel):
    session_token: str
    contact_name: str
    grants: list[PortalGrantSummaryOut]
    signing: PortalCanarySignOut

class PortalCanarySignSubmitIn(BaseModel):
    field_values: dict = Field(default_factory=dict)
    form_responses: dict | None = None
    consent: bool = True

class PortalCanarySignFormResponsesIn(BaseModel):
    responses: dict = Field(default_factory=dict)

class PortalCanarySignDeclineIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)

class PortalClientActionItemOut(BaseModel):
    kind: Literal["quote", "form", "canary_sign", "docusign"]
    id: uuid.UUID
    title: str
    status: str
    matter_label: str = ""
    badge: str = ""
    href_key: str = ""
    case_id: uuid.UUID | None = None

class PortalClientActionsOut(BaseModel):
    outstanding: list[PortalClientActionItemOut] = []
    complete: list[PortalClientActionItemOut] = []
    inactive: list[PortalClientActionItemOut] = []
