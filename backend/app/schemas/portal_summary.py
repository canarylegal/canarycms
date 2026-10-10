"""Staff Portal summary desk (firm-wide outstanding client actions)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PortalSummaryKind = Literal["quote", "form", "canary_sign", "docusign"]
PortalSummaryBucket = Literal["outstanding", "completed"]


class PortalSummaryOptionsOut(BaseModel):
    """Whether the Portal main-menu desk should be shown."""

    enabled: bool = False
    client_portal_enabled: bool = False
    canary_sign_enabled: bool = False
    docusign_enabled: bool = False


class PortalSummaryRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: PortalSummaryKind
    id: uuid.UUID
    case_id: uuid.UUID
    case_number: str | None = None
    client_name: str | None = None
    matter_description: str = ""
    title: str
    status: str
    contact_or_recipients: str = ""
    sent_by_display_name: str | None = None
    created_at: datetime | None = None


class PortalSummaryOut(BaseModel):
    bucket: PortalSummaryBucket = "outstanding"
    rows: list[PortalSummaryRowOut] = Field(default_factory=list)
