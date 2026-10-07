"""Case-level portal enablement checks (firm-wide × matter flag)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, ContactPortalGrant, FirmSettings

PORTAL_DISABLED_MSG = "Portal is not enabled for this matter."
FIRM_PORTAL_DISABLED_MSG = "Client portal is turned off for this firm."


def firm_client_portal_enabled(db: Session) -> bool:
    row = db.get(FirmSettings, 1)
    if row is None:
        return True
    return bool(row.client_portal_enabled)


def firm_canary_sign_enabled(db: Session) -> bool:
    row = db.get(FirmSettings, 1)
    if row is None:
        return True
    return bool(row.canary_sign_enabled)


def case_portal_enabled(db: Session, case_id: uuid.UUID) -> bool:
    """Effective portal: firm product on AND matter ``portal_enabled``."""
    if not firm_client_portal_enabled(db):
        return False
    case = db.get(Case, case_id)
    return bool(case and case.portal_enabled)


def require_case_portal_enabled(db: Session, case_id: uuid.UUID) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if not firm_client_portal_enabled(db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FIRM_PORTAL_DISABLED_MSG)
    if not case.portal_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PORTAL_DISABLED_MSG)
    return case


def filter_grants_for_portal_enabled_cases(
    db: Session,
    grants: list[ContactPortalGrant],
) -> list[ContactPortalGrant]:
    if not grants:
        return []
    if not firm_client_portal_enabled(db):
        return []
    case_ids = {g.case_id for g in grants}
    enabled_ids = set(
        db.execute(select(Case.id).where(Case.id.in_(case_ids), Case.portal_enabled.is_(True))).scalars().all()
    )
    return [g for g in grants if g.case_id in enabled_ids]


def active_portal_share_counts(db: Session, case_id: uuid.UUID) -> tuple[int, int]:
    from app.portal_service import grant_is_client_visible

    rows = db.execute(select(ContactPortalGrant).where(ContactPortalGrant.case_id == case_id)).scalars().all()
    active = [g for g in rows if grant_is_client_visible(db, g)]
    contacts = {g.contact_id for g in active}
    return len(active), len(contacts)
