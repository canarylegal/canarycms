"""Case-level portal enablement checks."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, ContactPortalGrant

PORTAL_DISABLED_MSG = "Portal is not enabled for this matter."


def case_portal_enabled(db: Session, case_id: uuid.UUID) -> bool:
    case = db.get(Case, case_id)
    return bool(case and case.portal_enabled)


def require_case_portal_enabled(db: Session, case_id: uuid.UUID) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if not case.portal_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PORTAL_DISABLED_MSG)
    return case


def filter_grants_for_portal_enabled_cases(
    db: Session,
    grants: list[ContactPortalGrant],
) -> list[ContactPortalGrant]:
    if not grants:
        return []
    case_ids = {g.case_id for g in grants}
    enabled_ids = set(
        db.execute(select(Case.id).where(Case.id.in_(case_ids), Case.portal_enabled.is_(True))).scalars().all()
    )
    return [g for g in grants if g.case_id in enabled_ids]


def active_portal_share_counts(db: Session, case_id: uuid.UUID) -> tuple[int, int]:
    from app.portal_service import grant_is_active

    rows = db.execute(select(ContactPortalGrant).where(ContactPortalGrant.case_id == case_id)).scalars().all()
    active = [g for g in rows if grant_is_active(g)]
    contacts = {g.contact_id for g in active}
    return len(active), len(contacts)
