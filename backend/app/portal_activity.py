"""In-app portal activity log for staff (per matter)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import PortalActivityEvent


def log_portal_activity(
    db: Session,
    *,
    case_id: uuid.UUID,
    action: str,
    summary: str,
    contact_id: uuid.UUID | None = None,
    grant_id: uuid.UUID | None = None,
) -> None:
    db.add(
        PortalActivityEvent(
            case_id=case_id,
            contact_id=contact_id,
            grant_id=grant_id,
            action=action,
            summary=summary.strip() or action,
        )
    )
    db.flush()
