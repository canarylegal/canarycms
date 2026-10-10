"""Pydantic schemas — commercial funds shortfall policy."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CommercialFundsSettingsOut(BaseModel):
    shortfall_policy: Literal["reject", "warn_override"] = "warn_override"


class CommercialFundsSettingsUpdate(BaseModel):
    shortfall_policy: Literal["reject", "warn_override"] | None = None
