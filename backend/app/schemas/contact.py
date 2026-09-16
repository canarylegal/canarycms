from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import (
    ContactType,
)

class ContactCreate(BaseModel):
    type: ContactType
    name: str = Field(min_length=1, max_length=300)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    # Person name fields
    title: str | None = Field(default=None, max_length=50)
    first_name: str | None = Field(default=None, max_length=150)
    middle_name: str | None = Field(default=None, max_length=150)
    last_name: str | None = Field(default=None, max_length=150)
    # Organisation fields
    company_name: str | None = Field(default=None, max_length=300)
    trading_name: str | None = Field(default=None, max_length=300)
    # Address
    address_line1: str | None = Field(default=None, max_length=300)
    address_line2: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=200)
    county: str | None = Field(default=None, max_length=150)
    postcode: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _organisation_requires_trading_name(self) -> ContactCreate:
        if self.type == ContactType.organisation and not (self.trading_name or "").strip():
            raise ValueError("Trading name is required for organisation contacts.")
        return self

class ContactUpdate(BaseModel):
    """PATCH `/contacts/{id}` — partial body; organisation trading-name rules enforced after merge in the router."""

    type: ContactType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=300)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, max_length=50)
    first_name: str | None = Field(default=None, max_length=150)
    middle_name: str | None = Field(default=None, max_length=150)
    last_name: str | None = Field(default=None, max_length=150)
    company_name: str | None = Field(default=None, max_length=300)
    trading_name: str | None = Field(default=None, max_length=300)
    address_line1: str | None = Field(default=None, max_length=300)
    address_line2: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=200)
    county: str | None = Field(default=None, max_length=150)
    postcode: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)

class ContactOut(BaseModel):
    id: uuid.UUID
    type: ContactType
    name: str
    email: EmailStr | None
    phone: str | None
    title: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    trading_name: str | None = None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    county: str | None = None
    postcode: str | None
    country: str | None
    created_at: datetime
    updated_at: datetime

class ContactMergeIn(BaseModel):
    source_contact_id: uuid.UUID
    """When true and a new client portal code is issued, e-mail it to the survivor contact."""
    send_email: bool = False

class ContactMergePreviewOut(BaseModel):
    survivor: ContactOut
    source: ContactOut
    survivor_matter_links: int
    source_matter_links: int
    survivor_grants: int
    source_grants: int
    survivor_client_portal_active: bool
    source_client_portal_active: bool
    survivor_matter_portal_active: int
    source_matter_portal_active: int
    email_mismatch: bool
    type_mismatch: bool
    will_reset_client_portal: bool
    will_reset_matter_portal_cases: int

class ContactMergeOut(BaseModel):
    survivor: ContactOut
    deleted_source_id: uuid.UUID
    client_portal_reset: bool
    new_client_access_code: str | None = None
    matter_portal_cases_reset: int
    grants_moved: int
    grants_deduped: int
    matter_links_moved: int
    email_sent: bool = False
    email_skip_reason: str | None = None

class CaseContactCreateFromGlobal(BaseModel):
    contact_id: uuid.UUID
    matter_contact_type: str = Field(min_length=1, max_length=200)
    matter_contact_reference: str | None = Field(default=None, max_length=500)
    lawyer_client_ids: list[uuid.UUID] | None = None
    letter_salutation: str | None = Field(default=None, max_length=64)
    letter_salutation_custom: str | None = Field(default=None, max_length=500)

class CaseContactUpdate(BaseModel):
    type: ContactType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=300)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, max_length=50)
    first_name: str | None = Field(default=None, max_length=150)
    middle_name: str | None = Field(default=None, max_length=150)
    last_name: str | None = Field(default=None, max_length=150)
    company_name: str | None = Field(default=None, max_length=300)
    trading_name: str | None = Field(default=None, max_length=300)
    address_line1: str | None = Field(default=None, max_length=300)
    address_line2: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=200)
    county: str | None = Field(default=None, max_length=150)
    postcode: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)
    matter_contact_type: str | None = Field(default=None, min_length=1, max_length=200)
    matter_contact_reference: str | None = Field(default=None, max_length=500)
    lawyer_client_ids: list[uuid.UUID] | None = None
    letter_salutation: str | None = Field(default=None, max_length=64)
    letter_salutation_custom: str | None = Field(default=None, max_length=500)
    push_to_global: bool = False

class CaseContactOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    contact_id: uuid.UUID | None
    is_linked_to_master: bool
    type: ContactType
    name: str
    email: EmailStr | None
    phone: str | None
    title: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    trading_name: str | None = None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    county: str | None = None
    postcode: str | None
    country: str | None
    matter_contact_type: str | None = None
    matter_contact_reference: str | None = None
    lawyer_client_ids: list[uuid.UUID] = Field(default_factory=list)
    letter_salutation: str | None = None
    letter_salutation_custom: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("lawyer_client_ids", mode="before")
    @classmethod
    def _lawyer_ids_from_json(cls, v: object) -> list[uuid.UUID]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        out: list[uuid.UUID] = []
        for x in v:
            out.append(uuid.UUID(str(x)))
        return out
