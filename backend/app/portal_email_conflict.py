"""Detect and resolve same-email portal login conflicts across contact cards."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.contact_merge_service import _merge_grants, _repoint
from app.models import (
    CanarySignRecipient,
    CaseContact,
    Contact,
    ContactPortalAccess,
    ContactPortalGrant,
    PortalFormSubmission,
    QuotePortalDelivery,
)
from app.portal_service import (
    bump_portal_session_version,
    contact_display_name,
    portal_access_is_active,
    staff_portal_access_code,
    utcnow,
)

ConflictResolution = Literal["join_existing", "revoke_other"]

PORTAL_EMAIL_CONFLICT_CODE = "portal_email_conflict"


@dataclass(frozen=True)
class PortalEmailConflict:
    other_contact: Contact
    other_access: ContactPortalAccess
    email: str
    other_grant_count: int


def find_active_portal_email_conflict(
    db: Session, *, contact_id: uuid.UUID, email: str | None = None
) -> PortalEmailConflict | None:
    """Return another contact with the same e-mail and an active portal login, if any.

    ``email`` overrides the contact's stored address (for pre-save checks on PATCH).
    """
    contact = db.get(Contact, contact_id)
    if contact is None:
        return None
    addr = (email if email is not None else (contact.email or "")).strip().lower()
    if not addr:
        return None
    rows = (
        db.execute(
            select(Contact, ContactPortalAccess)
            .join(ContactPortalAccess, ContactPortalAccess.contact_id == Contact.id)
            .where(func.lower(Contact.email) == addr, Contact.id != contact_id)
            .order_by(Contact.created_at.asc())
        )
        .all()
    )
    for other, access in rows:
        if portal_access_is_active(access):
            from app.contact_merge_service import _has_table

            grant_count = 0
            if _has_table(db, ContactPortalGrant.__tablename__):
                grant_count = int(
                    db.execute(
                        select(func.count())
                        .select_from(ContactPortalGrant)
                        .where(ContactPortalGrant.contact_id == other.id)
                    ).scalar_one()
                    or 0
                )
            return PortalEmailConflict(
                other_contact=other,
                other_access=access,
                email=addr,
                other_grant_count=grant_count,
            )
    return None


def conflict_http_detail(conflict: PortalEmailConflict) -> dict:
    other = conflict.other_contact
    return {
        "code": PORTAL_EMAIL_CONFLICT_CODE,
        "message": (
            f"Another contact ({contact_display_name(other)}) already has an active portal login "
            f"for {conflict.email}."
        ),
        "other_contact_id": str(other.id),
        "other_contact_name": contact_display_name(other),
        "other_email": conflict.email,
        "other_grant_count": conflict.other_grant_count,
    }


def raise_if_email_conflicts_with_portal_login(
    db: Session, *, contact_id: uuid.UUID, new_email: str | None
) -> None:
    """Block saving an e-mail that already has an active portal login on another contact."""
    addr = (new_email or "").strip().lower()
    if not addr:
        return
    contact = db.get(Contact, contact_id)
    if contact is None:
        return
    current = (contact.email or "").strip().lower()
    if addr == current:
        return
    conflict = find_active_portal_email_conflict(db, contact_id=contact_id, email=addr)
    if conflict is not None:
        raise_portal_email_conflict(conflict)


def raise_portal_email_conflict(conflict: PortalEmailConflict) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=conflict_http_detail(conflict),
    )


def disable_portal_access_for_conflict(
    db: Session,
    *,
    other_contact_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    superseded_by_contact_id: uuid.UUID,
) -> None:
    """Disable the earlier contact's portal login (keep grants/history)."""
    row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == other_contact_id)
    ).scalar_one_or_none()
    if row is None:
        return
    row.enabled = False
    row.code_enc = None
    row.failed_attempts = 0
    row.locked_until = None
    bump_portal_session_version(row)
    row.updated_at = utcnow()
    db.add(row)
    log_event(
        db,
        actor_user_id=actor_user_id,
        action="contact.portal.access.superseded",
        entity_type="contact",
        entity_id=str(other_contact_id),
        meta={"superseded_by_contact_id": str(superseded_by_contact_id)},
    )
    db.flush()


def _repoint_case_scoped(
    db: Session,
    model,
    contact_column,
    case_column,
    *,
    source_id: uuid.UUID,
    survivor_id: uuid.UUID,
    case_id: uuid.UUID,
) -> int:
    rows = list(
        db.execute(
            select(model).where(contact_column == source_id, case_column == case_id)
        ).scalars().all()
    )
    for row in rows:
        setattr(row, contact_column.key, survivor_id)
        db.add(row)
    if rows:
        db.flush()
    return len(rows)


def _merge_grants_for_case(
    db: Session,
    *,
    source_id: uuid.UUID,
    survivor_id: uuid.UUID,
    case_id: uuid.UUID,
) -> tuple[int, int]:
    """Move source grants for one matter onto survivor; dedupe identical folders."""
    from app.contact_merge_service import _delete_row, _has_table, _uuid_key
    from app.portal_grant_views import ContactPortalGrantView

    survivor_grants = list(
        db.execute(
            select(ContactPortalGrant).where(
                ContactPortalGrant.contact_id == survivor_id,
                ContactPortalGrant.case_id == case_id,
            )
        ).scalars().all()
    )
    source_grants = list(
        db.execute(
            select(ContactPortalGrant).where(
                ContactPortalGrant.contact_id == source_id,
                ContactPortalGrant.case_id == case_id,
            )
        ).scalars().all()
    )

    def _grant_key(g: ContactPortalGrant) -> tuple[str, str]:
        return (_uuid_key(g.case_id), (g.folder_path or "").strip())

    by_key = {_grant_key(g): g for g in survivor_grants}
    moved = 0
    deduped = 0
    for grant in source_grants:
        key = _grant_key(grant)
        existing = by_key.get(key)
        if existing is not None:
            existing.can_download = bool(existing.can_download) or bool(grant.can_download)
            existing.can_upload = bool(existing.can_upload) or bool(grant.can_upload)
            if not (existing.label or "").strip() and (grant.label or "").strip():
                existing.label = grant.label
            if existing.expires_at is not None:
                if grant.expires_at is None or grant.expires_at > existing.expires_at:
                    existing.expires_at = grant.expires_at
            db.add(existing)
            if _has_table(db, ContactPortalGrantView.__tablename__):
                for view in db.execute(
                    select(ContactPortalGrantView).where(ContactPortalGrantView.grant_id == grant.id)
                ).scalars().all():
                    _delete_row(db, ContactPortalGrantView, view)
            _delete_row(db, ContactPortalGrant, grant)
            deduped += 1
        else:
            if _has_table(db, ContactPortalGrantView.__tablename__):
                for view in db.execute(
                    select(ContactPortalGrantView).where(ContactPortalGrantView.grant_id == grant.id)
                ).scalars().all():
                    _delete_row(db, ContactPortalGrantView, view)
            grant.contact_id = survivor_id
            db.add(grant)
            by_key[key] = grant
            moved += 1
    db.flush()
    return moved, deduped


def join_existing_portal_login(
    db: Session,
    *,
    contact_id: uuid.UUID,
    conflict: PortalEmailConflict,
    case_id: uuid.UUID | None,
    actor_user_id: uuid.UUID,
) -> tuple[str, bool]:
    """Keep the other contact's login; move portal content onto them.

    Returns ``(access_code, matter_contact_relinked)``.
    """
    other_id = conflict.other_contact.id
    if case_id is not None:
        _merge_grants_for_case(db, source_id=contact_id, survivor_id=other_id, case_id=case_id)
        _repoint_case_scoped(
            db,
            QuotePortalDelivery,
            QuotePortalDelivery.contact_id,
            QuotePortalDelivery.case_id,
            source_id=contact_id,
            survivor_id=other_id,
            case_id=case_id,
        )
        _repoint_case_scoped(
            db,
            PortalFormSubmission,
            PortalFormSubmission.contact_id,
            PortalFormSubmission.case_id,
            source_id=contact_id,
            survivor_id=other_id,
            case_id=case_id,
        )
        from app.models import CanarySignRequest

        canary_rows = list(
            db.execute(
                select(CanarySignRecipient)
                .join(CanarySignRequest, CanarySignRequest.id == CanarySignRecipient.signing_request_id)
                .where(
                    CanarySignRecipient.contact_id == contact_id,
                    CanarySignRequest.case_id == case_id,
                )
            ).scalars().all()
        )
        for row in canary_rows:
            row.contact_id = other_id
            db.add(row)
        if canary_rows:
            db.flush()
    else:
        _merge_grants(db, source_id=contact_id, survivor_id=other_id)
        _repoint(
            db,
            QuotePortalDelivery,
            QuotePortalDelivery.contact_id,
            source_id=contact_id,
            survivor_id=other_id,
        )
        _repoint(
            db,
            PortalFormSubmission,
            PortalFormSubmission.contact_id,
            source_id=contact_id,
            survivor_id=other_id,
        )
        _repoint(
            db,
            CanarySignRecipient,
            CanarySignRecipient.contact_id,
            source_id=contact_id,
            survivor_id=other_id,
        )

    matter_relinked = False
    if case_id is not None:
        other_already = db.execute(
            select(CaseContact.id).where(
                CaseContact.case_id == case_id, CaseContact.contact_id == other_id
            )
        ).scalar_one_or_none()
        if other_already is None:
            rows = list(
                db.execute(
                    select(CaseContact).where(
                        CaseContact.case_id == case_id, CaseContact.contact_id == contact_id
                    )
                ).scalars().all()
            )
            for cc in rows:
                cc.contact_id = other_id
                cc.updated_at = utcnow()
                db.add(cc)
                matter_relinked = True
            if rows:
                db.flush()

    # Drop any inactive/disabled access row on this contact so it cannot be re-enabled casually.
    own = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)
    ).scalar_one_or_none()
    if own is not None and not portal_access_is_active(own):
        own.enabled = False
        own.code_enc = None
        bump_portal_session_version(own)
        db.add(own)

    code = staff_portal_access_code(conflict.other_access) or ""
    log_event(
        db,
        actor_user_id=actor_user_id,
        action="contact.portal.access.join_existing",
        entity_type="contact",
        entity_id=str(contact_id),
        meta={
            "other_contact_id": str(other_id),
            "case_id": str(case_id) if case_id else None,
            "matter_contact_relinked": matter_relinked,
        },
    )
    db.flush()
    return code, matter_relinked


def require_no_unresolved_portal_email_conflict(
    db: Session,
    *,
    contact_id: uuid.UUID,
    conflict_resolution: ConflictResolution | None,
) -> PortalEmailConflict | None:
    """If a conflict exists and no resolution was chosen, raise 409. Otherwise return it."""
    conflict = find_active_portal_email_conflict(db, contact_id=contact_id)
    if conflict is None:
        return None
    if conflict_resolution is None:
        raise_portal_email_conflict(conflict)
    if conflict_resolution not in ("join_existing", "revoke_other"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conflict_resolution; use join_existing or revoke_other",
        )
    return conflict
