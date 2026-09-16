from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class DocusignIntegrationSettingsOut(BaseModel):
    enabled: bool
    use_demo: bool
    allow_tier_a: bool
    allow_tier_b: bool
    allow_tier_c: bool
    allow_wes: bool
    allow_qes: bool
    account_id: str | None = None
    integration_key: str | None = None
    user_id: str | None = None
    rsa_private_key_configured: bool = False
    connect_hmac_secret_configured: bool = False
    api_base_uri: str | None = None
    configured: bool = False
    cost_standard_pence: int | None = None
    cost_wes_pence: int | None = None
    cost_qes_pence: int | None = None

class DocusignIntegrationSettingsUpdate(BaseModel):
    enabled: bool | None = None
    use_demo: bool | None = None
    allow_tier_a: bool | None = None
    allow_tier_b: bool | None = None
    allow_tier_c: bool | None = None
    allow_wes: bool | None = None
    allow_qes: bool | None = None
    account_id: str | None = Field(default=None, max_length=2000)
    integration_key: str | None = Field(default=None, max_length=2000)
    user_id: str | None = Field(default=None, max_length=2000)
    rsa_private_key: str | None = Field(default=None, max_length=20000)
    connect_hmac_secret: str | None = Field(default=None, max_length=2000)
    api_base_uri: str | None = Field(default=None, max_length=2000)
    cost_standard_pence: int | None = Field(default=None, ge=0)
    cost_wes_pence: int | None = Field(default=None, ge=0)
    cost_qes_pence: int | None = Field(default=None, ge=0)

class DocusignTemplateOut(BaseModel):
    template_id: str
    name: str
    description: str | None = None
    roles: list[str] = []

class DocusignSendRecipientIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    email: EmailStr
    routing_order: int = Field(default=1, ge=1, le=99)
    role_name: str | None = Field(default=None, max_length=100)
    case_contact_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None

class DocusignSendIn(BaseModel):
    source_file_id: uuid.UUID | None = None
    template_id: str | None = Field(default=None, max_length=64)
    envelope_subject: str | None = Field(default=None, max_length=500)
    document_tier: Literal["a", "b", "c"] = "a"
    signature_level: Literal["standard", "wes", "qes"] = "standard"
    recipients: list[DocusignSendRecipientIn] = Field(min_length=1, max_length=20)

class DocusignVoidIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

class DocusignSigningRecipientOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    routing_order: int
    role_name: str | None = None
    status: str
    completed_at: datetime | None = None

class DocusignSigningRequestOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    source_file_id: uuid.UUID | None = None
    source_filename: str = ""
    docusign_envelope_id: str | None = None
    docusign_template_id: str | None = None
    envelope_subject: str
    document_tier: str
    signature_level: str
    status: str
    status_detail: str | None = None
    signed_file_id: uuid.UUID | None = None
    certificate_file_id: uuid.UUID | None = None
    completed_at: datetime | None = None
    voided_at: datetime | None = None
    created_at: datetime | None = None
    recipients: list[DocusignSigningRecipientOut] = []

class DocusignStaffOptionsOut(BaseModel):
    enabled: bool
    allow_tier_a: bool
    allow_tier_b: bool
    allow_tier_c: bool
    allow_wes: bool
    allow_qes: bool

class DocusignMenuRowOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None = None
    matter_description: str = ""
    envelope_subject: str
    source_filename: str = ""
    status: str
    status_detail: str | None = None
    sent_by_display_name: str | None = None
    recipients_summary: str = ""
    created_at: datetime
    completed_at: datetime | None = None
    voided_at: datetime | None = None

class PortalDocusignSigningOut(BaseModel):
    id: uuid.UUID
    envelope_subject: str
    status: str
    can_sign: bool
    recipient_id: uuid.UUID
    sign_token: str
