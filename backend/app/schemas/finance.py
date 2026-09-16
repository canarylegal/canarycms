from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class FinanceItemTemplateCreate(BaseModel):
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    direction: Literal["debit", "credit"]
    sort_order: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}

class FinanceItemTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    direction: Literal["debit", "credit"] | None = None
    sort_order: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}

class FinanceItemTemplateOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    direction: Literal["debit", "credit"]
    sort_order: int

class FinanceCategoryTemplateCreate(BaseModel):
    matter_sub_type_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}

class FinanceCategoryTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}

class FinanceCategoryTemplateOut(BaseModel):
    id: uuid.UUID
    matter_sub_type_id: uuid.UUID
    name: str
    sort_order: int
    credit_only: bool = False
    items: list[FinanceItemTemplateOut] = []

class FinanceTemplateOut(BaseModel):
    matter_sub_type_id: uuid.UUID
    categories: list[FinanceCategoryTemplateOut]

class FinanceItemCreate(BaseModel):
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    direction: Literal["debit", "credit"]
    sort_order: int = Field(default=0, ge=0)
    vat_treatment: Literal["included", "plus_vat"] | None = None

    model_config = {"extra": "forbid"}

class FinanceItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    direction: Literal["debit", "credit"] | None = None
    amount_pence: int | None = Field(default=None, ge=0)
    vat_pence: int | None = Field(default=None, ge=0)
    vat_treatment: Literal["included", "plus_vat"] | None = None
    sort_order: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}

class FinanceItemOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    template_item_id: uuid.UUID | None
    name: str
    direction: Literal["debit", "credit"]
    amount_pence: int | None
    vat_pence: int | None = None
    vat_treatment: Literal["included", "plus_vat"] | None = None
    sort_order: int

class FinanceCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}

class FinanceCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}

class FinanceCategoryOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    template_category_id: uuid.UUID | None
    name: str
    sort_order: int
    credit_only: bool = False
    items: list[FinanceItemOut] = []

class FinanceOut(BaseModel):
    case_id: uuid.UUID
    categories: list[FinanceCategoryOut]
    has_finance_preset: bool = False
    has_quote_snapshot: bool = False
    vat_rate_bps: int = 2000
