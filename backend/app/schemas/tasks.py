from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import (
    CaseTaskStatus,
)

CaseTaskPriority = Literal["low", "normal", "high"]


class CaseNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)

class CaseNoteUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)

class CaseNoteOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    author_user_id: uuid.UUID
    body: str
    created_at: datetime
    updated_at: datetime

class MatterSubTypeStandardTaskCreate(BaseModel):
    matter_sub_type_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    sort_order: int = 0

class MatterSubTypeStandardTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    sort_order: int | None = None

class MatterSubTypeStandardTaskOut(BaseModel):
    id: uuid.UUID
    matter_sub_type_id: uuid.UUID | None
    title: str
    sort_order: int
    is_system: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class CaseTaskCreate(BaseModel):
    """Custom task: set title. Standard task: set standard_task_id (title from template unless ``title`` overrides)."""

    title: str | None = Field(default=None, max_length=300)
    standard_task_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=20000)
    due_at: datetime | None = None
    assigned_to_user_id: uuid.UUID | None = None
    priority: CaseTaskPriority = "normal"
    is_private: bool = False

    @model_validator(mode="after")
    def title_or_standard(self) -> CaseTaskCreate:
        if self.standard_task_id is None and (self.title is None or not str(self.title).strip()):
            raise ValueError("title is required when standard_task_id is not set")
        return self

class CaseTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    status: CaseTaskStatus | None = None
    due_at: datetime | None = None
    assigned_to_user_id: uuid.UUID | None = None
    priority: CaseTaskPriority | None = None
    is_private: bool | None = None
    standard_task_id: uuid.UUID | None = None

class CaseTaskOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    created_by_user_id: uuid.UUID
    title: str
    description: str | None
    status: CaseTaskStatus
    due_at: datetime | None
    standard_task_id: uuid.UUID | None = None
    assigned_to_user_id: uuid.UUID | None = None
    assigned_display_name: str | None = None
    priority: CaseTaskPriority = "normal"
    case_event_id: uuid.UUID | None = None
    is_private: bool = False
    created_at: datetime
    updated_at: datetime

class CaseTimeEntryCreate(BaseModel):
    work_date: date
    duration_minutes: int = Field(ge=6)
    description: str = Field(min_length=1, max_length=4000)
    user_id: uuid.UUID | None = None
    non_billable: bool = False

    model_config = {"extra": "forbid"}

class CaseTimeEntryUpdate(BaseModel):
    work_date: date | None = None
    duration_minutes: int | None = Field(default=None, ge=6)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    user_id: uuid.UUID | None = None
    non_billable: bool | None = None

    model_config = {"extra": "forbid"}

class CaseTimeEntryOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    user_id: uuid.UUID
    user_display_name: str
    created_by_user_id: uuid.UUID
    work_date: date
    duration_minutes: int
    duration_tenths: int
    description: str
    status: Literal["unbilled", "billed", "written_off"]
    invoice_line_id: uuid.UUID | None = None
    non_billable: bool = False
    charge_rate_pence_per_hour: int | None = None
    value_pence: int | None = None
    created_at: datetime
    updated_at: datetime

class TaskMenuRowOut(BaseModel):
    """Case tasks for the global Tasks menu (one row per task)."""

    id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str | None
    matter_type_label: str
    task_title: str
    date: datetime
    assigned_display_name: str | None = None
    priority: CaseTaskPriority = "normal"
    status: CaseTaskStatus
    is_private: bool = False
    standard_task_id: uuid.UUID | None = None
    """Resolved template title for Kanban columns (standard tasks)."""
    standard_task_category_title: str | None = None
