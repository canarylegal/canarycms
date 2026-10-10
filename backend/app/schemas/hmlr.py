"""Pydantic schemas for HM Land Registry integration."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class HmlrIntegrationSettingsOut(BaseModel):
    enabled: bool
    sandbox: bool
    username: str | None = None
    password_configured: bool = False
    customer_reference: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    configured: bool = False
    # True until a Gateway client certificate is installed / live calls are possible.
    mock_mode: bool = True


class HmlrIntegrationSettingsUpdate(BaseModel):
    enabled: bool | None = None
    sandbox: bool | None = None
    username: str | None = None
    password: str | None = None
    customer_reference: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None


class HmlrOrderOut(BaseModel):
    id: uuid.UUID
    title_number: str
    external_reference: str
    want_register: bool
    want_title_plan: bool
    state: str
    fee_pence: int
    error_message: str | None = None
    register_file_id: uuid.UUID | None = None
    plan_file_id: uuid.UUID | None = None
    sandbox: bool
    placed_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class HmlrSummaryOut(BaseModel):
    configured: bool
    enabled: bool
    sandbox: bool
    mock_mode: bool
    orders: list[HmlrOrderOut] = Field(default_factory=list)
    suggested_title_numbers: list[str] = Field(default_factory=list)


class HmlrCreateOrderIn(BaseModel):
    title_number: str = Field(min_length=1, max_length=32)
    want_register: bool = True
    want_title_plan: bool = True
    external_reference: str | None = Field(default=None, max_length=128)
