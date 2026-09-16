from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class MatterSubTypeEventTemplateOut(BaseModel):
    id: uuid.UUID
    matter_sub_type_id: uuid.UUID
    name: str
    sort_order: int
    notify_on_day: bool = True
    notify_every_n: int | None = None
    notify_every_unit: Literal["days", "weeks", "months"] | None = None
    created_at: datetime
    updated_at: datetime

class CalendarEventTemplatePickOut(BaseModel):
    """Matter sub-type calendar line template for quick-fill on the main (CalDAV) calendar."""

    id: uuid.UUID
    matter_sub_type_id: uuid.UUID
    matter_sub_type_name: str
    name: str
    sort_order: int
    notify_on_day: bool = True
    notify_every_n: int | None = None
    notify_every_unit: Literal["days", "weeks", "months"] | None = None

class MatterSubTypeEventTemplateCreate(BaseModel):
    matter_sub_type_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = 0
    notify_on_day: bool = True
    notify_every_n: int | None = Field(default=None, ge=1, le=365)
    notify_every_unit: Literal["days", "weeks", "months"] | None = None

class MatterSubTypeEventTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None
    notify_on_day: bool | None = None
    notify_every_n: int | None = Field(default=None, ge=1, le=365)
    notify_every_unit: Literal["days", "weeks", "months"] | None = None

class CaseEventOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    template_id: uuid.UUID | None
    name: str
    sort_order: int
    event_date: date | None
    event_all_day: bool = True
    event_start_time: time | None = None
    """ISO start/end for CalDAV sync (UTC Z); only set when ``event_date`` is set."""
    calendar_block_start: str | None = None
    calendar_block_end: str | None = None
    calendar_block_all_day: bool | None = None
    track_in_calendar: bool = False
    calendar_event_uid: str | None = None
    email_alert_enabled: bool = False
    created_at: datetime
    updated_at: datetime

class CaseEventsOut(BaseModel):
    case_id: uuid.UUID
    events: list[CaseEventOut]

class CaseEventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    event_date: date | None = None
    event_all_day: bool = True
    event_start_time: time | None = None
    track_in_calendar: bool = False
    email_alert: bool = False

    @field_validator("event_date", mode="before")
    @classmethod
    def _empty_event_date_create(cls, v: object) -> object:
        if v == "" or v is None:
            return None
        return v

class CaseEventUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    event_date: date | None = None
    event_all_day: bool | None = None
    event_start_time: time | None = None
    track_in_calendar: bool | None = None
    calendar_event_uid: str | None = Field(default=None, max_length=512)
    email_alert: bool | None = None

    @field_validator("event_date", mode="before")
    @classmethod
    def _empty_event_date_to_none(cls, v: object) -> object:
        if v == "" or v is None:
            return None
        return v
