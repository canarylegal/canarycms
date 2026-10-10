"""Pydantic schemas for install-wide Searches provider selection."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.casera import CaseraIntegrationSettingsOut


class SearchProviderOptionOut(BaseModel):
    id: str
    label: str


class SearchIntegrationSettingsOut(BaseModel):
    provider: str = "none"
    available_providers: list[SearchProviderOptionOut] = Field(default_factory=list)
    casera: CaseraIntegrationSettingsOut | None = None


class SearchIntegrationSettingsUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
