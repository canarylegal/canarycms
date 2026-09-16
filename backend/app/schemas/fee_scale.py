from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class FeeScaleOut(BaseModel):
    id: uuid.UUID
    name: str
    reference: str
    vat_rate_bps: int = 2000
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None
    matter_head_type_name: str | None = None
    matter_sub_type_name: str | None = None
    scope_summary: str | None = None
    is_favorited: bool = False
    created_at: datetime
    updated_at: datetime

class FeeScaleFavoriteUpdate(BaseModel):
    favorited: bool

class FeeScaleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    reference: str = Field(min_length=1, max_length=200)
    vat_rate_bps: int = Field(default=2000, ge=0, le=10000)
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None

class FeeScaleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    reference: str | None = Field(default=None, min_length=1, max_length=200)
    vat_rate_bps: int | None = Field(default=None, ge=0, le=10000)
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None

class FeeScaleLineOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    line_kind: Literal["section_header", "item", "vat", "subtotal", "total"]
    amount_kind: Literal["fixed", "editable", "band"] | None = None
    default_amount_pence: int | None = None
    band_set_id: uuid.UUID | None = None
    vat_treatment: Literal["included", "plus_vat"] = "included"
    sort_order: int

class FeeScaleCategoryOut(BaseModel):
    id: uuid.UUID
    fee_scale_id: uuid.UUID
    name: str
    sort_order: int
    lines: list[FeeScaleLineOut] = Field(default_factory=list)

class FeeScaleBandRowOut(BaseModel):
    id: uuid.UUID
    band_set_id: uuid.UUID
    min_value_pence: int
    max_value_pence: int | None = None
    amount_pence: int
    sort_order: int

class FeeScaleBandSetOut(BaseModel):
    id: uuid.UUID
    fee_scale_id: uuid.UUID
    name: str
    sort_order: int
    rows: list[FeeScaleBandRowOut] = Field(default_factory=list)

class FeeScaleDetailOut(FeeScaleOut):
    categories: list[FeeScaleCategoryOut] = Field(default_factory=list)
    band_sets: list[FeeScaleBandSetOut] = Field(default_factory=list)

class FeeScaleCategoryCreate(BaseModel):
    fee_scale_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = 0

class FeeScaleCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None

class FeeScaleLineCreate(BaseModel):
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=300)
    line_kind: Literal["section_header", "item", "vat", "subtotal", "total"]
    amount_kind: Literal["fixed", "editable", "band"] | None = None
    default_amount_pence: int | None = None
    band_set_id: uuid.UUID | None = None
    vat_treatment: Literal["included", "plus_vat"] = "included"
    sort_order: int = 0

class FeeScaleLineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    line_kind: Literal["section_header", "item", "vat", "subtotal", "total"] | None = None
    amount_kind: Literal["fixed", "editable", "band"] | None = None
    default_amount_pence: int | None = None
    band_set_id: uuid.UUID | None = None
    vat_treatment: Literal["included", "plus_vat"] | None = None
    sort_order: int | None = None

class FeeScaleBandSetCreate(BaseModel):
    fee_scale_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = 0

class FeeScaleBandSetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None

class FeeScaleBandRowCreate(BaseModel):
    band_set_id: uuid.UUID
    min_value_pence: int = Field(ge=0)
    max_value_pence: int | None = Field(default=None, ge=0)
    amount_pence: int = Field(ge=0)
    sort_order: int = 0

class FeeScaleBandRowUpdate(BaseModel):
    min_value_pence: int | None = Field(default=None, ge=0)
    max_value_pence: int | None = None
    amount_pence: int | None = Field(default=None, ge=0)
    sort_order: int | None = None

class QuotePreviewLineOut(BaseModel):
    key: str | None = None
    line_id: uuid.UUID | None = None
    name: str
    line_kind: str
    amount_pence: int | None = None
    amount_display: str | None = None
    editable: bool = False
    is_bold: bool = False
    vat_pence: int | None = None
    vat_treatment: Literal["included", "plus_vat"] | None = None
    amount_kind: str | None = None
    band_set_id: uuid.UUID | None = None
    sort_order: int = 0

class QuotePreviewCategoryOut(BaseModel):
    key: str
    category_id: uuid.UUID | None = None
    name: str
    sort_order: int
    lines: list[QuotePreviewLineOut]

class QuotePreviewOut(BaseModel):
    fee_scale_id: uuid.UUID
    property_value_pence: int | None = None
    needs_property_value: bool = False
    lines: list[QuotePreviewLineOut]
    categories: list[QuotePreviewCategoryOut] = Field(default_factory=list)

class QuoteDraftLineIn(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    line_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=512)
    line_kind: str
    amount_kind: str | None = None
    amount_pence: int | None = Field(default=None, ge=0)
    vat_treatment: Literal["included", "plus_vat"] = "included"
    band_set_id: uuid.UUID | None = None
    sort_order: int = 0

class QuoteDraftCategoryIn(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    category_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=256)
    sort_order: int = 0
    lines: list[QuoteDraftLineIn] = Field(default_factory=list)

class QuotePreviewIn(BaseModel):
    property_value_pence: int | None = Field(default=None, ge=0)
    line_overrides: dict[str, int] = Field(default_factory=dict)
    amount_overrides: dict[str, int] = Field(default_factory=dict)
    draft: list[QuoteDraftCategoryIn] | None = None

class ComposeQuoteLineIn(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    line_kind: str
    amount_pence: int | None = Field(default=None, ge=0)
    vat_pence: int | None = Field(default=None, ge=0)
    is_bold: bool = False

class ComposeQuoteIn(BaseModel):
    original_filename: str = Field(min_length=1, max_length=512)
    folder: str = ""
    fee_scale_id: uuid.UUID | None = None
    case_contact_id: uuid.UUID | None = None
    global_contact_id: uuid.UUID | None = None
    precedent_merge_all_clients: bool = False
    property_value_pence: int | None = Field(default=None, ge=0)
    line_overrides: dict[str, int] = Field(default_factory=dict)
    amount_overrides: dict[str, int] = Field(default_factory=dict)
    draft: list[QuoteDraftCategoryIn] | None = None
    quote_lines: list[ComposeQuoteLineIn] | None = None
