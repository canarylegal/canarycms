from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import (
    PrecedentKind,
)

class PrecedentCategoryOut(BaseModel):
    id: uuid.UUID
    matter_sub_type_id: uuid.UUID
    name: str
    sort_order: int
    created_at: datetime
    updated_at: datetime

class PrecedentCategoryFlatOut(PrecedentCategoryOut):
    """Admin list: categories with sub-type label for grouping in the UI."""

    matter_sub_type_name: str

class PrecedentCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = 0

class PrecedentCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None

class PrecedentOut(BaseModel):
    id: uuid.UUID
    name: str
    reference: str
    kind: PrecedentKind
    original_filename: str
    mime_type: str
    category_id: uuid.UUID | None = None
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None
    category_name: str | None = None
    matter_head_type_name: str | None = None
    matter_sub_type_name: str | None = None
    scope_summary: str = ""
    created_at: datetime

class PrecedentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    reference: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: uuid.UUID | None = None
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None
