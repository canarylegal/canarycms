"""Staff management of per-contact portal access codes and folder grants."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.alert_dispatch import AlertKind, dispatch_alert
from app.canary_public_url import canary_public_url
from app.file_storage import sanitize_folder_path
from app.models import Case, Contact, ContactPortalAccess, ContactPortalGrant, User
from app.portal_service import (
    contact_display_name,
    default_grant_label,
    generate_access_code,
    hash_access_code,
    portal_access_is_active,
    staff_portal_access_code,
    store_portal_access_code,
    utcnow,
)
from app.schemas import (
    ContactPortalAccessActionIn,
    ContactPortalAccessCreateOut,
    ContactPortalAccessEmailIn,
    ContactPortalAccessOut,
    ContactPortalAccessUpdateIn,
    ContactPortalGrantCreateIn,
    ContactPortalGrantOut,
    ContactPortalGrantUpdateIn,
)

router = APIRouter(prefix="/contacts/{contact_id}/portal", tags=["contact-portal"])


def _get_contact_or_404(db: Session, contact_id: uuid.UUID) -> Contact:
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


def _grant_out(db: Session, grant: ContactPortalGrant) -> ContactPortalGrantOut:
    case = db.get(Case, grant.case_id)
    return ContactPortalGrantOut(
        id=grant.id,
        contact_id=grant.contact_id,
        case_id=grant.case_id,
        case_title=case.title if case else "",
        folder_path=grant.folder_path or "",
        label=grant.label,
        can_download=grant.can_download,
        can_upload=grant.can_upload,
        expires_at=grant.expires_at,
        created_at=grant.created_at,
    )


def _portal_public_url() -> str:
    return f"{canary_public_url().rstrip('/')}/portal"


def _notify_portal_access_email(db: Session, contact: Contact, access_code: str, *, actor_user_id: uuid.UUID) -> bool:
    email = (contact.email or "").strip()
    if not email:
        return False
    return dispatch_alert(
        db,
        AlertKind.portal_contact_access,
        to_email=email,
        context={
            "contact_name": contact_display_name(contact),
            "access_code": access_code,
            "portal_url": _portal_public_url(),
        },
        actor_user_id=actor_user_id,
    )


def _notify_portal_folder_granted(db: Session, contact: Contact, grant: ContactPortalGrant, *, actor_user_id: uuid.UUID) -> bool:
    email = (contact.email or "").strip()
    if not email:
        return False
    return dispatch_alert(
        db,
        AlertKind.portal_contact_folder,
        to_email=email,
        context={
            "contact_name": contact_display_name(contact),
            "area_label": default_grant_label(db, grant),
            "portal_url": _portal_public_url(),
        },
        actor_user_id=actor_user_id,
    )


@router.get("/access", response_model=ContactPortalAccessOut)
def get_contact_portal_access(
    contact_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactPortalAccessOut:
    _get_contact_or_404(db, contact_id)
    row = db.execute(select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)).scalar_one_or_none()
    if row is None:
        return ContactPortalAccessOut(
            enabled=False,
            expires_at=None,
            last_login_at=None,
            locked_until=None,
            has_access=False,
            access_code=None,
            access_record_exists=False,
        )
    return ContactPortalAccessOut(
        enabled=row.enabled,
        expires_at=row.expires_at,
        last_login_at=row.last_login_at,
        locked_until=row.locked_until,
        has_access=portal_access_is_active(row),
        access_code=staff_portal_access_code(row) if portal_access_is_active(row) else None,
        access_record_exists=True,
    )


@router.post("/access", response_model=ContactPortalAccessCreateOut, status_code=status.HTTP_201_CREATED)
def create_contact_portal_access(
    contact_id: uuid.UUID,
    payload: ContactPortalAccessActionIn = ContactPortalAccessActionIn(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactPortalAccessCreateOut:
    _get_contact_or_404(db, contact_id)
    contact = db.get(Contact, contact_id)
    assert contact is not None
    existing = db.execute(select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)).scalar_one_or_none()
    if existing is not None and portal_access_is_active(existing):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Portal access already exists; rotate the code instead")
    code = generate_access_code()
    if existing is None:
        row = ContactPortalAccess(
            contact_id=contact_id,
            enabled=True,
            created_by_user_id=user.id,
        )
        db.add(row)
    else:
        row = existing
        row.enabled = True
        row.failed_attempts = 0
        row.locked_until = None
        row.updated_at = utcnow()
    store_portal_access_code(row, code)
    db.add(row)
    db.commit()
    action = "contact.portal.access.create" if existing is None else "contact.portal.access.reactivate"
    log_event(
        db,
        actor_user_id=user.id,
        action=action,
        entity_type="contact",
        entity_id=str(contact_id),
    )
    email_sent = False
    if payload.send_email:
        email_sent = _notify_portal_access_email(db, contact, code, actor_user_id=user.id)
    return ContactPortalAccessCreateOut(access_code=code, enabled=True, expires_at=None, email_sent=email_sent)


@router.post("/access/email", status_code=status.HTTP_204_NO_CONTENT)
def send_contact_portal_access_email(
    contact_id: uuid.UUID,
    payload: ContactPortalAccessEmailIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Send portal access invite e-mail when staff opts in (code must match current access)."""
    contact = _get_contact_or_404(db, contact_id)
    row = db.execute(select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)).scalar_one_or_none()
    if row is None or not portal_access_is_active(row):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal access is not active for this contact")
    if row.code_sha256 != hash_access_code(payload.access_code.strip()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Access code does not match")
    if not _notify_portal_access_email(db, contact, payload.access_code.strip(), actor_user_id=user.id):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not send e-mail (check contact e-mail address and Admin → E-mail alert settings).",
        )


@router.post("/access/rotate", response_model=ContactPortalAccessCreateOut)
def rotate_contact_portal_access(
    contact_id: uuid.UUID,
    payload: ContactPortalAccessActionIn = ContactPortalAccessActionIn(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactPortalAccessCreateOut:
    _get_contact_or_404(db, contact_id)
    contact = db.get(Contact, contact_id)
    assert contact is not None
    row = db.execute(select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)).scalar_one_or_none()
    code = generate_access_code()
    if row is None:
        row = ContactPortalAccess(
            contact_id=contact_id,
            enabled=True,
            created_by_user_id=user.id,
        )
        db.add(row)
    store_portal_access_code(row, code)
    row.enabled = True
    row.failed_attempts = 0
    row.locked_until = None
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="contact.portal.access.rotate",
        entity_type="contact",
        entity_id=str(contact_id),
    )
    email_sent = False
    if payload.send_email:
        email_sent = _notify_portal_access_email(db, contact, code, actor_user_id=user.id)
    return ContactPortalAccessCreateOut(access_code=code, enabled=True, expires_at=row.expires_at, email_sent=email_sent)


@router.patch("/access", response_model=ContactPortalAccessOut)
def update_contact_portal_access(
    contact_id: uuid.UUID,
    payload: ContactPortalAccessUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactPortalAccessOut:
    _get_contact_or_404(db, contact_id)
    row = db.execute(select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal access is not set up for this contact")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(
        db,
        actor_user_id=user.id,
        action="contact.portal.access.update",
        entity_type="contact",
        entity_id=str(contact_id),
        meta=data,
    )
    return ContactPortalAccessOut(
        enabled=row.enabled,
        expires_at=row.expires_at,
        last_login_at=row.last_login_at,
        locked_until=row.locked_until,
        has_access=portal_access_is_active(row),
        access_code=staff_portal_access_code(row) if portal_access_is_active(row) else None,
        access_record_exists=True,
    )


@router.delete("/access", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact_portal_access(
    contact_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _get_contact_or_404(db, contact_id)
    row = db.execute(select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)).scalar_one_or_none()
    grants = db.execute(select(ContactPortalGrant).where(ContactPortalGrant.contact_id == contact_id)).scalars().all()
    for grant in grants:
        db.delete(grant)
    if row is None:
        if grants:
            db.commit()
        return
    db.delete(row)
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="contact.portal.access.delete",
        entity_type="contact",
        entity_id=str(contact_id),
        meta={"grants_removed": len(grants)},
    )


@router.get("/grants", response_model=list[ContactPortalGrantOut])
def list_contact_portal_grants(
    contact_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ContactPortalGrantOut]:
    _get_contact_or_404(db, contact_id)
    rows = db.execute(select(ContactPortalGrant).where(ContactPortalGrant.contact_id == contact_id).order_by(ContactPortalGrant.created_at.desc())).scalars().all()
    return [_grant_out(db, g) for g in rows]


@router.post("/grants", response_model=ContactPortalGrantOut, status_code=status.HTTP_201_CREATED)
def create_contact_portal_grant(
    contact_id: uuid.UUID,
    payload: ContactPortalGrantCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactPortalGrantOut:
    _get_contact_or_404(db, contact_id)
    contact = db.get(Contact, contact_id)
    assert contact is not None
    require_case_access(payload.case_id, user, db)
    folder = sanitize_folder_path(payload.folder_path)
    grant = ContactPortalGrant(
        contact_id=contact_id,
        case_id=payload.case_id,
        folder_path=folder,
        label=(payload.label or "").strip() or None,
        can_download=payload.can_download,
        can_upload=payload.can_upload,
        expires_at=payload.expires_at,
        created_by_user_id=user.id,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    log_event(
        db,
        actor_user_id=user.id,
        action="contact.portal.grant.create",
        entity_type="contact_portal_grant",
        entity_id=str(grant.id),
        meta={"contact_id": str(contact_id), "case_id": str(payload.case_id), "folder_path": folder},
    )
    email_sent = False
    if payload.send_email:
        email_sent = _notify_portal_folder_granted(db, contact, grant, actor_user_id=user.id)
    out = _grant_out(db, grant)
    return out.model_copy(update={"email_sent": email_sent})


@router.patch("/grants/{grant_id}", response_model=ContactPortalGrantOut)
def update_contact_portal_grant(
    contact_id: uuid.UUID,
    grant_id: uuid.UUID,
    payload: ContactPortalGrantUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactPortalGrantOut:
    _get_contact_or_404(db, contact_id)
    grant = db.get(ContactPortalGrant, grant_id)
    if not grant or grant.contact_id != contact_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")
    require_case_access(grant.case_id, user, db)
    data = payload.model_dump(exclude_unset=True)
    if "folder_path" in data and data["folder_path"] is not None:
        data["folder_path"] = sanitize_folder_path(data["folder_path"])
    if "label" in data and data["label"] is not None:
        data["label"] = data["label"].strip() or None
    for key, value in data.items():
        setattr(grant, key, value)
    grant.updated_at = utcnow()
    db.add(grant)
    db.commit()
    db.refresh(grant)
    log_event(
        db,
        actor_user_id=user.id,
        action="contact.portal.grant.update",
        entity_type="contact_portal_grant",
        entity_id=str(grant.id),
        meta=data,
    )
    return _grant_out(db, grant)


@router.delete("/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact_portal_grant(
    contact_id: uuid.UUID,
    grant_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _get_contact_or_404(db, contact_id)
    grant = db.get(ContactPortalGrant, grant_id)
    if not grant or grant.contact_id != contact_id:
        return
    require_case_access(grant.case_id, user, db)
    db.delete(grant)
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="contact.portal.grant.delete",
        entity_type="contact_portal_grant",
        entity_id=str(grant_id),
    )
