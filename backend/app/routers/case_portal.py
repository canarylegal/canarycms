"""Case-scoped client portal helpers (folder sharing, activity, staff notification settings)."""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.file_storage import sanitize_folder_path
from app.models import Case, CaseContact, Contact, ContactPortalAccess, ContactPortalGrant, PortalActivityEvent, User
from app.portal_notifications import (
    ALERTS_NOT_CONFIGURED_MSG,
    notify_portal_contacts_files_added_batch,
    set_portal_staff_recipients,
)
from app.portal_case import active_portal_share_counts, require_case_portal_enabled
from app.portal_service import (
    contact_display_name,
    grant_is_active,
    list_active_grants_for_contact,
    portal_access_is_active,
)
from app.schemas import (
    CasePortalActivityOut,
    CasePortalFolderShareContactOut,
    CasePortalNotificationSettingsIn,
    CasePortalNotificationSettingsOut,
    CasePortalNotifyFilesIn,
    CasePortalNotifyFilesOut,
    CasePortalPreviewContactOut,
    CasePortalPreviewIn,
    CasePortalPreviewOut,
    CasePortalShareStatusOut,
    CasePortalStaffUserOut,
)
from app.security import create_portal_preview_exchange_token

router = APIRouter(prefix="/cases/{case_id}/portal", tags=["case-portal"])


def _require_portal(case_id: uuid.UUID, user: User, db: Session) -> None:
    require_case_access(case_id, user, db)
    require_case_portal_enabled(db, case_id)


def _staff_users_out(db: Session, user_ids: list[uuid.UUID]) -> list[CasePortalStaffUserOut]:
    if not user_ids:
        return []
    rows = db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    by_id = {row.id: row for row in rows}
    out: list[CasePortalStaffUserOut] = []
    for uid in user_ids:
        row = by_id.get(uid)
        out.append(
            CasePortalStaffUserOut(
                id=uid,
                display_name=(row.display_name if row else "") or (row.email if row else "") or "Unknown user",
                email=(row.email if row else "") or "",
            )
        )
    return out


def _notification_settings_out(db: Session, user_ids: list[uuid.UUID]) -> CasePortalNotificationSettingsOut:
    ids = list(user_ids)
    return CasePortalNotificationSettingsOut(staff_user_ids=ids, staff_users=_staff_users_out(db, ids))


def _grant_for_exact_folder(
    grants: list[ContactPortalGrant],
    *,
    contact_id: uuid.UUID,
    folder_path: str,
) -> ContactPortalGrant | None:
    folder = sanitize_folder_path(folder_path)
    for grant in grants:
        if grant.contact_id != contact_id:
            continue
        if not grant_is_active(grant):
            continue
        if sanitize_folder_path(grant.folder_path) == folder:
            return grant
    return None


def _portal_access_by_contact_ids(
    db: Session,
    contact_ids: list[uuid.UUID],
) -> dict[uuid.UUID, ContactPortalAccess]:
    if not contact_ids:
        return {}
    rows = (
        db.execute(select(ContactPortalAccess).where(ContactPortalAccess.contact_id.in_(contact_ids)))
        .scalars()
        .all()
    )
    return {row.contact_id: row for row in rows}


def _preview_contacts_for_case(db: Session, case_id: uuid.UUID) -> list[CasePortalPreviewContactOut]:
    case_contacts = (
        db.execute(select(CaseContact).where(CaseContact.case_id == case_id).order_by(CaseContact.name.asc()))
        .scalars()
        .all()
    )
    grants = db.execute(select(ContactPortalGrant).where(ContactPortalGrant.case_id == case_id)).scalars().all()
    contact_ids = [cc.contact_id for cc in case_contacts if cc.contact_id]
    access_by_contact = _portal_access_by_contact_ids(db, contact_ids)
    grant_counts: dict[uuid.UUID, int] = {}
    for grant in grants:
        if not grant_is_active(grant):
            continue
        grant_counts[grant.contact_id] = grant_counts.get(grant.contact_id, 0) + 1

    out: list[CasePortalPreviewContactOut] = []
    seen: set[uuid.UUID] = set()
    for cc in case_contacts:
        if not cc.contact_id or cc.contact_id in seen:
            continue
        access = access_by_contact.get(cc.contact_id)
        if access is None or not portal_access_is_active(access):
            continue
        shared = grant_counts.get(cc.contact_id, 0)
        if shared <= 0:
            continue
        seen.add(cc.contact_id)
        out.append(
            CasePortalPreviewContactOut(
                contact_id=cc.contact_id,
                contact_name=(cc.name or "").strip() or "Contact",
                shared_folder_count=shared,
            )
        )
    return out


def _validate_preview_contact(db: Session, case_id: uuid.UUID, contact_id: uuid.UUID) -> Contact:
    on_case = db.execute(
        select(CaseContact).where(CaseContact.case_id == case_id, CaseContact.contact_id == contact_id)
    ).scalar_one_or_none()
    if on_case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact is not on this matter")
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    access = db.execute(select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)).scalar_one_or_none()
    if access is None or not portal_access_is_active(access):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Portal access is not active for this contact")
    grants = [
        g
        for g in db.execute(
            select(ContactPortalGrant).where(
                ContactPortalGrant.case_id == case_id,
                ContactPortalGrant.contact_id == contact_id,
            )
        ).scalars().all()
        if grant_is_active(g)
    ]
    if not grants:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This contact has no shared folders on this matter",
        )
    all_grants = list_active_grants_for_contact(db, contact_id)
    if not all_grants:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No document areas are available for this contact")
    return contact


def _any_active_grant_on_case(
    grants: list[ContactPortalGrant],
    *,
    contact_id: uuid.UUID,
) -> ContactPortalGrant | None:
    active = [g for g in grants if g.contact_id == contact_id and grant_is_active(g)]
    if not active:
        return None
    downloadable = [g for g in active if g.can_download]
    return downloadable[0] if downloadable else active[0]


@router.get("/folder-share", response_model=list[CasePortalFolderShareContactOut])
def list_case_portal_folder_share_contacts(
    case_id: uuid.UUID,
    folder_path: str = Query(default=""),
    grant_scope: str = Query(default="folder"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CasePortalFolderShareContactOut]:
    _require_portal(case_id, user, db)
    folder = sanitize_folder_path(folder_path)
    matter_scope = grant_scope.strip().lower() == "matter"
    case_contacts = (
        db.execute(select(CaseContact).where(CaseContact.case_id == case_id).order_by(CaseContact.name.asc()))
        .scalars()
        .all()
    )
    grants = db.execute(select(ContactPortalGrant).where(ContactPortalGrant.case_id == case_id)).scalars().all()
    contact_ids = [cc.contact_id for cc in case_contacts if cc.contact_id]
    access_by_contact = _portal_access_by_contact_ids(db, contact_ids)

    out: list[CasePortalFolderShareContactOut] = []
    seen: set[uuid.UUID] = set()
    for cc in case_contacts:
        if not cc.contact_id or cc.contact_id in seen:
            continue
        access = access_by_contact.get(cc.contact_id)
        if access is None or not portal_access_is_active(access):
            continue
        seen.add(cc.contact_id)
        if matter_scope:
            grant = _any_active_grant_on_case(grants, contact_id=cc.contact_id)
        else:
            grant = _grant_for_exact_folder(grants, contact_id=cc.contact_id, folder_path=folder)
        out.append(
            CasePortalFolderShareContactOut(
                case_contact_id=cc.id,
                contact_id=cc.contact_id,
                contact_name=(cc.name or "").strip() or "Contact",
                has_grant=grant is not None,
                grant_id=grant.id if grant else None,
            )
        )
    return out


@router.get("/share-status", response_model=CasePortalShareStatusOut)
def case_portal_share_status(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CasePortalShareStatusOut:
    case = require_case_access(case_id, user, db)
    grant_count, contact_count = active_portal_share_counts(db, case_id)
    return CasePortalShareStatusOut(
        portal_enabled=bool(case.portal_enabled),
        active_grant_count=grant_count,
        contact_count=contact_count,
    )


@router.get("/activity", response_model=list[CasePortalActivityOut])
def list_case_portal_activity(
    case_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CasePortalActivityOut]:
    _require_portal(case_id, user, db)
    rows = (
        db.execute(
            select(PortalActivityEvent)
            .where(PortalActivityEvent.case_id == case_id)
            .order_by(PortalActivityEvent.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    out: list[CasePortalActivityOut] = []
    for row in rows:
        cname = None
        if row.contact_id:
            c = db.get(Contact, row.contact_id)
            cname = contact_display_name(c) if c else None
        out.append(
            CasePortalActivityOut(
                id=row.id,
                action=row.action,
                summary=row.summary,
                contact_name=cname,
                created_at=row.created_at,
            )
        )
    return out


@router.get("/notification-settings", response_model=CasePortalNotificationSettingsOut)
def get_case_portal_notification_settings(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CasePortalNotificationSettingsOut:
    _require_portal(case_id, user, db)
    from app.models import CasePortalStaffRecipient

    ids = (
        db.execute(select(CasePortalStaffRecipient.user_id).where(CasePortalStaffRecipient.case_id == case_id))
        .scalars()
        .all()
    )
    return _notification_settings_out(db, ids)


@router.put("/notification-settings", response_model=CasePortalNotificationSettingsOut)
def update_case_portal_notification_settings(
    case_id: uuid.UUID,
    payload: CasePortalNotificationSettingsIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CasePortalNotificationSettingsOut:
    _require_portal(case_id, user, db)
    kept = set_portal_staff_recipients(db, case_id, payload.staff_user_ids)
    db.commit()
    return _notification_settings_out(db, kept)


@router.get("/preview-contacts", response_model=list[CasePortalPreviewContactOut])
def list_case_portal_preview_contacts(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CasePortalPreviewContactOut]:
    _require_portal(case_id, user, db)
    return _preview_contacts_for_case(db, case_id)


@router.post("/preview", response_model=CasePortalPreviewOut)
def create_case_portal_preview(
    case_id: uuid.UUID,
    payload: CasePortalPreviewIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CasePortalPreviewOut:
    _require_portal(case_id, user, db)
    contact = _validate_preview_contact(db, case_id, payload.contact_id)
    exchange_token = create_portal_preview_exchange_token(
        contact_id=str(contact.id),
        case_id=str(case_id),
        staff_user_id=str(user.id),
    )
    log_event(
        db,
        actor_user_id=user.id,
        action="portal.preview.issue",
        entity_type="contact",
        entity_id=str(contact.id),
        meta={"case_id": str(case_id), "contact_id": str(contact.id)},
    )
    db.commit()
    cname = contact_display_name(contact)
    preview_path = f"/portal?staff_preview=1&preview_exchange={quote(exchange_token, safe='')}"
    return CasePortalPreviewOut(
        exchange_token=exchange_token,
        contact_name=cname,
        preview_url=preview_path,
    )


@router.post("/notify-files-added", response_model=CasePortalNotifyFilesOut)
def case_portal_notify_files_added(
    case_id: uuid.UUID,
    payload: CasePortalNotifyFilesIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CasePortalNotifyFilesOut:
    _require_portal(case_id, user, db)
    result = notify_portal_contacts_files_added_batch(
        db,
        case_id=case_id,
        folder_path=payload.folder_path,
        filenames=payload.filenames,
        actor_user_id=user.id,
    )
    db.commit()
    return CasePortalNotifyFilesOut(
        contacts_notified=result.contacts_notified,
        alerts_skipped_reason=result.alerts_skipped_reason,
    )
