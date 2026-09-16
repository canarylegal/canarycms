from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import (
    CaseLockMode,
    CaseStatus,
    LetterheadStyle,
)

class FirmSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = 1
    trading_name: str = ""
    registered_company_name: str | None = None
    addr_line1: str | None = None
    addr_line2: str | None = None
    town_city: str | None = None
    county: str | None = None
    postcode: str | None = None
    letterhead_style: LetterheadStyle = LetterheadStyle.preprinted
    letterhead_original_filename: str | None = None
    quote_letterhead_style: LetterheadStyle = LetterheadStyle.preprinted
    quote_letterhead_original_filename: str | None = None
    portal_logo_configured: bool = False
    portal_logo_original_filename: str | None = None
    portal_background_color: str | None = None
    default_signature_configured: bool = False
    default_signature_original_filename: str | None = None
    default_signature_scale: int = Field(default=7, ge=1, le=10)
    mandate_two_factor: bool = False
    mandate_password_rotation: bool = False
    password_rotation_days: int | None = None
    client_bank_account_name: str | None = None
    client_bank_sort_code: str | None = None
    client_bank_account_number_last4: str | None = None
    client_bank_account_number: str | None = None

class MergeCodeCatalogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    description: str
    sort_order: int

class MergeCodeCatalogRowIn(BaseModel):
    code: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=16000)

class MergeCodeCatalogBulkUpdate(BaseModel):
    items: list[MergeCodeCatalogRowIn]

class MergeCodeCatalogImportResult(BaseModel):
    updated: int
    skipped_unknown: int

class FirmSettingsUpdate(BaseModel):
    trading_name: str | None = Field(default=None, max_length=300)
    registered_company_name: str | None = Field(default=None, max_length=400)
    addr_line1: str | None = Field(default=None, max_length=300)
    addr_line2: str | None = Field(default=None, max_length=300)
    town_city: str | None = Field(default=None, max_length=200)
    county: str | None = Field(default=None, max_length=150)
    postcode: str | None = Field(default=None, max_length=50)
    letterhead_style: LetterheadStyle | None = None
    quote_letterhead_style: LetterheadStyle | None = None
    default_signature_scale: int | None = Field(default=None, ge=1, le=10)
    # Empty string clears to the product default; omit to leave unchanged.
    portal_background_color: str | None = Field(default=None, max_length=32)
    mandate_two_factor: bool | None = None
    mandate_password_rotation: bool | None = None
    password_rotation_days: int | None = Field(default=None, ge=1, le=3650)
    client_bank_account_name: str | None = Field(default=None, max_length=200)
    client_bank_sort_code: str | None = Field(default=None, max_length=16)
    client_bank_account_number_last4: str | None = Field(default=None, max_length=4)
    client_bank_account_number: str | None = Field(default=None, max_length=20)

class MatterHeadTypeVisibilityUpdate(BaseModel):
    is_hidden: bool

class MatterSubTypeMenuOut(BaseModel):
    id: uuid.UUID
    name: str

class MatterSubTypeMenuCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

class MatterSubTypeMenuUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

class MatterSubTypeOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str | None
    menus: list[MatterSubTypeMenuOut] = []

class MatterHeadTypeOut(BaseModel):
    id: uuid.UUID
    name: str
    is_hidden: bool = False
    sub_types: list[MatterSubTypeOut] = []

class MatterSubTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

class MatterSubTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    prefix: str | None = None

class CaseCreate(BaseModel):
    matter_description: str = Field(min_length=1, max_length=300)
    status: CaseStatus = CaseStatus.open
    practice_area: str | None = Field(default=None, max_length=200)
    matter_sub_type_id: uuid.UUID
    fee_earner_user_id: uuid.UUID
    source_id: uuid.UUID | None = None
    source_name: str | None = Field(default=None, max_length=200)
    portal_enabled: bool = False

    @field_validator("status")
    @classmethod
    def new_matter_status_open_or_quote_only(cls, v: CaseStatus) -> CaseStatus:
        if v not in (CaseStatus.open, CaseStatus.quote):
            raise ValueError("New matters may only be created as Active (open) or Quote.")
        return v

class CaseUpdate(BaseModel):
    matter_description: str | None = Field(default=None, min_length=1, max_length=300)
    fee_earner_user_id: uuid.UUID | None = None
    status: CaseStatus | None = None
    practice_area: str | None = Field(default=None, max_length=200)
    matter_sub_type_id: uuid.UUID | None = None
    matter_head_type_id: uuid.UUID | None = None
    is_locked: bool | None = None
    lock_mode: CaseLockMode | None = None
    source_id: uuid.UUID | None = None
    source_name: str | None = Field(default=None, max_length=200)
    portal_enabled: bool | None = None

class MatterMenuItemOut(BaseModel):
    id: uuid.UUID
    name: str

class CaseOut(BaseModel):
    id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str
    fee_earner_user_id: uuid.UUID
    status: CaseStatus
    practice_area: str | None
    matter_sub_type_id: uuid.UUID | None
    matter_head_type_id: uuid.UUID | None
    matter_sub_type_name: str | None
    matter_head_type_name: str | None
    matter_menus: list[MatterMenuItemOut] = Field(default_factory=list)
    source_id: uuid.UUID | None = None
    source_name: str | None = None
    created_by: uuid.UUID
    is_locked: bool
    lock_mode: CaseLockMode
    portal_enabled: bool = False
    created_at: datetime
    updated_at: datetime

class MatterContactTypeOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    sort_order: int
    is_system: bool

    model_config = ConfigDict(from_attributes=True)

class CaseSourceOut(BaseModel):
    id: uuid.UUID
    name: str
    sort_order: int
    is_system: bool

    model_config = ConfigDict(from_attributes=True)

class CaseSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

class CaseSourceAdminUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None

class MatterContactTypeAdminCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    sort_order: int = 0

class MatterContactTypeAdminUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None

class CasePropertyUK(BaseModel):
    line1: str | None = Field(default=None, max_length=300)
    line2: str | None = Field(default=None, max_length=300)
    town: str | None = Field(default=None, max_length=200)
    county: str | None = Field(default=None, max_length=200)
    postcode: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)

class CasePropertyPayload(BaseModel):
    """Stored in case_property_details.payload."""

    is_non_postal: bool = False
    uk: CasePropertyUK = Field(default_factory=CasePropertyUK)
    free_lines: list[str] = Field(default_factory=lambda: ["", "", "", "", "", ""])
    title_numbers: list[str] = Field(default_factory=list)
    tenure: Literal["freehold", "leasehold", "commonhold"] | None = None
    existing_lender_case_contact_id: uuid.UUID | None = None
    charge_date: str | None = Field(default=None, max_length=10)

class CasePropertyDetailsOut(BaseModel):
    has_details: bool
    payload: CasePropertyPayload
    updated_at: datetime | None = None
