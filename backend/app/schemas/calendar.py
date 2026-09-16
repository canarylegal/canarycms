from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class CalendarEventOut(BaseModel):
    id: str
    uid: str
    title: str
    start: str
    end: str
    all_day: bool = False
    description: str | None = None
    calendar_name: str | None = None
    calendar_id: str | None = None
    can_edit: bool = True
    # Canary-only category (not in iCal).
    category_id: uuid.UUID | None = None
    category_name: str | None = None
    category_color: str | None = None
    # Matter-linked row merged into the feed (not from Radicale).
    case_id: uuid.UUID | None = None
    case_event_id: uuid.UUID | None = None
    track_in_calendar: bool | None = None
    matter_template_id: uuid.UUID | None = None
    email_alert_enabled: bool = False

class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    start: datetime | date
    end: datetime | date
    all_day: bool = False
    description: str | None = Field(default=None, max_length=20000)
    calendar_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    email_alert: bool = False
    matter_sub_type_event_template_id: uuid.UUID | None = None

class CalendarEventPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    start: datetime | date | None = None
    end: datetime | date | None = None
    all_day: bool | None = None
    description: str | None = Field(default=None, max_length=20000)
    category_id: uuid.UUID | None = None
    email_alert: bool | None = None
    matter_sub_type_event_template_id: uuid.UUID | None = None

class CalendarCategoryOut(BaseModel):
    id: uuid.UUID
    calendar_id: uuid.UUID
    name: str
    color: str | None = None

class CalendarCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=20)

class CalendarCategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=20)

class CalendarCategorySyncOut(BaseModel):
    updated: int
    cleared: int

class CalendarOwnerMini(BaseModel):
    id: uuid.UUID
    display_name: str
    email: EmailStr

class UserCalendarOut(BaseModel):
    id: uuid.UUID
    name: str
    radicale_slug: str
    is_public: bool
    access: Literal["owner", "read", "write"]
    source: Literal["owned", "share", "subscription"]
    owner: CalendarOwnerMini

class CalendarShareOut(BaseModel):
    grantee_user_id: uuid.UUID
    grantee_display_name: str
    grantee_email: EmailStr
    can_write: bool

class CalendarCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

class CalendarPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_public: bool | None = None

class CalendarShareCreate(BaseModel):
    grantee_user_id: uuid.UUID
    can_write: bool = False

class CalendarSubscribeIn(BaseModel):
    calendar_id: uuid.UUID

class CalendarDirectoryRow(BaseModel):
    id: uuid.UUID
    name: str
    owner: CalendarOwnerMini
    is_public: bool
    shared_directly: bool
    already_in_my_list: bool
    can_subscribe: bool
