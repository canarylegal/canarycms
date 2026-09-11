"""Staff management of matter-scoped portal exchange access for non-client contacts."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.alert_dispatch import AlertKind, dispatch_alert, firm_alerts_configured, portal_public_url
from app.audit import log_event
from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.models import Case, Contact, MatterPortalAccess, User
from app.portal_case import require_case_portal_enabled
from app.portal_notifications import ALERTS_NOT_CONFIGURED_MSG
from app.portal_service import (
    allocate_unique_access_code,
    bump_matter_portal_session_version,
    client_matter_description,
    contact_display_name,
    ensure_matter_portal_access,
    get_matter_portal_access,
    matter_portal_access_is_active,
    require_exchange_matter_contact,
    resolve_matter_contact_email,
    staff_matter_portal_access_code,
    store_matter_portal_access_code,
    utcnow,
)
from app.schemas import MatterPortalAccessActionIn, MatterPortalAccessCreateOut, MatterPortalAccessOut

router = APIRouter(prefix="/cases/{case_id}/contacts/{contact_id}/matter-portal", tags=["matter-portal"])


def _access_out(row: MatterPortalAccess | None, *, case_id: uuid.UUID, contact_id: uuid.UUID) -> MatterPortalAccessOut:
    if row is None:
        return MatterPortalAccessOut(
            enabled=False,
            expires_at=None,
            last_login_at=None,
            locked_until=None,
            has_access=False,
            access_code=None,
            access_record_exists=False,
            notify_folder_shared=True,
            case_id=case_id,
            contact_id=contact_id,
        )
    return MatterPortalAccessOut(
        enabled=bool(row.enabled),
        expires_at=row.expires_at,
        last_login_at=row.last_login_at,
        locked_until=row.locked_until,
        has_access=matter_portal_access_is_active(row),
        access_code=staff_matter_portal_access_code(row) if matter_portal_access_is_active(row) else None,
        access_record_exists=True,
        notify_folder_shared=bool(row.notify_folder_shared),
        case_id=case_id,
        contact_id=contact_id,
    )


def _notify_matter_exchange_email(
    db: Session,
    *,
    case: Case,
    contact: Contact,
    access_code: str,
    area_label: str,
    actor_user_id: uuid.UUID,
) -> tuple[bool, str | None]:
    if not firm_alerts_configured(db):
        return False, ALERTS_NOT_CONFIGURED_MSG
    email = resolve_matter_contact_email(db, case_id=case.id, contact_id=contact.id)
    if not email:
        return False, "Contact has no e-mail address."
    sent = dispatch_alert(
        db,
        AlertKind.portal_matter_exchange_shared,
        to_email=email,
        context={
            "contact_name": contact_display_name(contact),
            "matter_label": client_matter_description(case),
            "area_label": area_label,
            "portal_url": portal_public_url(),
            "access_code": access_code,
        },
        actor_user_id=actor_user_id,
    )
    return sent, None if sent else ALERTS_NOT_CONFIGURED_MSG


@router.get("/access", response_model=MatterPortalAccessOut)
def get_matter_portal_access_endpoint(
    case_id: uuid.UUID,
    contact_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MatterPortalAccessOut:
    require_case_access(case_id, user, db)
    require_exchange_matter_contact(db, case_id=case_id, contact_id=contact_id)
    row = get_matter_portal_access(db, case_id=case_id, contact_id=contact_id)
    return _access_out(row, case_id=case_id, contact_id=contact_id)


@router.post("/access", response_model=MatterPortalAccessCreateOut, status_code=status.HTTP_201_CREATED)
def create_matter_portal_access(
    case_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: MatterPortalAccessActionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MatterPortalAccessCreateOut:
    require_case_access(case_id, user, db)
    require_case_portal_enabled(db, case_id)
    case = db.get(Case, case_id)
    contact = db.get(Contact, contact_id)
    if case is None or contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    row, _newly, code = ensure_matter_portal_access(
        db, case_id=case_id, contact_id=contact_id, actor_user_id=user.id
    )
    if not code:
        code = staff_matter_portal_access_code(row) or allocate_unique_access_code(db)
        if not staff_matter_portal_access_code(row):
            store_matter_portal_access_code(row, code)
            db.add(row)
    db.commit()
    db.refresh(row)
    email_sent = False
    email_skip_reason: str | None = None
    if payload.send_email:
        email_sent, email_skip_reason = _notify_matter_exchange_email(
            db,
            case=case,
            contact=contact,
            access_code=code,
            area_label="Matter documents",
            actor_user_id=user.id,
        )
        db.commit()
    return MatterPortalAccessCreateOut(
        access_code=code,
        enabled=True,
        expires_at=row.expires_at,
        email_sent=email_sent,
        email_skip_reason=email_skip_reason,
        case_id=case_id,
        contact_id=contact_id,
    )


@router.post("/access/rotate", response_model=MatterPortalAccessCreateOut)
def rotate_matter_portal_access(
    case_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: MatterPortalAccessActionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MatterPortalAccessCreateOut:
    require_case_access(case_id, user, db)
    require_case_portal_enabled(db, case_id)
    require_exchange_matter_contact(db, case_id=case_id, contact_id=contact_id)
    case = db.get(Case, case_id)
    contact = db.get(Contact, contact_id)
    if case is None or contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    row = get_matter_portal_access(db, case_id=case_id, contact_id=contact_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter portal access not found")
    code = allocate_unique_access_code(db)
    row.enabled = True
    row.failed_attempts = 0
    row.locked_until = None
    store_matter_portal_access_code(row, code)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(
        db,
        actor_user_id=user.id,
        action="matter.portal.access.rotate",
        entity_type="matter_portal_access",
        entity_id=str(row.id),
        meta={"case_id": str(case_id), "contact_id": str(contact_id)},
    )
    email_sent = False
    email_skip_reason: str | None = None
    if payload.send_email:
        email_sent, email_skip_reason = _notify_matter_exchange_email(
            db,
            case=case,
            contact=contact,
            access_code=code,
            area_label="Matter documents",
            actor_user_id=user.id,
        )
    db.commit()
    return MatterPortalAccessCreateOut(
        access_code=code,
        enabled=True,
        expires_at=row.expires_at,
        email_sent=email_sent,
        email_skip_reason=email_skip_reason,
        case_id=case_id,
        contact_id=contact_id,
    )


@router.delete("/access", status_code=status.HTTP_204_NO_CONTENT)
def revoke_matter_portal_access(
    case_id: uuid.UUID,
    contact_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_case_access(case_id, user, db)
    require_exchange_matter_contact(db, case_id=case_id, contact_id=contact_id)
    row = get_matter_portal_access(db, case_id=case_id, contact_id=contact_id)
    if row is None:
        return
    row.enabled = False
    bump_matter_portal_session_version(row)
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="matter.portal.access.revoke",
        entity_type="matter_portal_access",
        entity_id=str(row.id),
        meta={"case_id": str(case_id), "contact_id": str(contact_id)},
    )
    db.commit()
