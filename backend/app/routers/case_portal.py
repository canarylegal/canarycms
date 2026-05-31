"""Case-scoped client portal helpers (folder sharing from matter documents)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.file_storage import sanitize_folder_path
from app.models import CaseContact, ContactPortalAccess, ContactPortalGrant, User
from app.portal_service import grant_is_active, portal_access_is_active
from app.schemas import CasePortalFolderShareContactOut

router = APIRouter(prefix="/cases/{case_id}/portal", tags=["case-portal"])


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


@router.get("/folder-share", response_model=list[CasePortalFolderShareContactOut])
def list_case_portal_folder_share_contacts(
    case_id: uuid.UUID,
    folder_path: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CasePortalFolderShareContactOut]:
    """Portal-enabled case contacts and whether they have a grant for ``folder_path``."""
    require_case_access(case_id, user, db)
    folder = sanitize_folder_path(folder_path)
    case_contacts = (
        db.execute(select(CaseContact).where(CaseContact.case_id == case_id).order_by(CaseContact.name.asc()))
        .scalars()
        .all()
    )
    grants = db.execute(select(ContactPortalGrant).where(ContactPortalGrant.case_id == case_id)).scalars().all()
    access_rows = db.execute(select(ContactPortalAccess)).scalars().all()
    access_by_contact = {row.contact_id: row for row in access_rows}

    out: list[CasePortalFolderShareContactOut] = []
    seen: set[uuid.UUID] = set()
    for cc in case_contacts:
        if not cc.contact_id or cc.contact_id in seen:
            continue
        access = access_by_contact.get(cc.contact_id)
        if access is None or not portal_access_is_active(access):
            continue
        seen.add(cc.contact_id)
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
