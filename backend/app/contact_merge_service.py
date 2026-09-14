"""Merge a duplicate global contact into a survivor contact."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.models import (
    CanarySignRecipient,
    CaseContact,
    CaseInvoice,
    Contact,
    ContactPortalAccess,
    ContactPortalGrant,
    DocusignSigningRecipient,
    LedgerEntry,
    MatterPortalAccess,
    PortalActivityEvent,
    PortalFormSubmission,
    PortalLoginOtp,
    QuotePortalDelivery,
    User,
)
from app.portal_grant_views import ContactPortalGrantView
from app.portal_service import (
    allocate_unique_access_code,
    matter_portal_access_is_active,
    portal_access_is_active,
    store_matter_portal_access_code,
    store_portal_access_code,
    utcnow,
)


def _has_table(db: Session, name: str) -> bool:
    bind = db.get_bind()
    return bool(inspect(bind).has_table(name))


@dataclass
class ContactMergePreview:
    survivor: Contact
    source: Contact
    survivor_matter_links: int
    source_matter_links: int
    survivor_grants: int
    source_grants: int
    survivor_client_portal_active: bool
    source_client_portal_active: bool
    survivor_matter_portal_active: int
    source_matter_portal_active: int
    email_mismatch: bool
    type_mismatch: bool
    will_reset_client_portal: bool
    will_reset_matter_portal_cases: int


@dataclass
class ContactMergeResult:
    survivor: Contact
    deleted_source_id: uuid.UUID
    client_portal_reset: bool
    new_client_access_code: str | None
    matter_portal_cases_reset: int
    grants_moved: int
    grants_deduped: int
    matter_links_moved: int


def _require_contact(db: Session, contact_id: uuid.UUID) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


def _active_client_portal(db: Session, contact_id: uuid.UUID) -> ContactPortalAccess | None:
    row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)
    ).scalar_one_or_none()
    if row is None or not portal_access_is_active(row):
        return None
    return row


def _active_matter_portal_count(db: Session, contact_id: uuid.UUID) -> int:
    rows = db.execute(
        select(MatterPortalAccess).where(MatterPortalAccess.contact_id == contact_id)
    ).scalars().all()
    return sum(1 for r in rows if matter_portal_access_is_active(r))


def _matter_portal_case_ids(db: Session, contact_id: uuid.UUID) -> set[uuid.UUID]:
    rows = db.execute(
        select(MatterPortalAccess).where(MatterPortalAccess.contact_id == contact_id)
    ).scalars().all()
    return {r.case_id for r in rows if matter_portal_access_is_active(r)}


def preview_contact_merge(
    db: Session,
    *,
    survivor_id: uuid.UUID,
    source_id: uuid.UUID,
) -> ContactMergePreview:
    if survivor_id == source_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot merge a contact into itself.",
        )
    survivor = _require_contact(db, survivor_id)
    source = _require_contact(db, source_id)

    survivor_portal = _active_client_portal(db, survivor_id) is not None
    source_portal = _active_client_portal(db, source_id) is not None
    survivor_matter_cases = _matter_portal_case_ids(db, survivor_id)
    source_matter_cases = _matter_portal_case_ids(db, source_id)
    matter_cases_to_reset = survivor_matter_cases | source_matter_cases

    survivor_email = (survivor.email or "").strip().lower()
    source_email = (source.email or "").strip().lower()
    email_mismatch = bool(survivor_email and source_email and survivor_email != source_email)

    return ContactMergePreview(
        survivor=survivor,
        source=source,
        survivor_matter_links=int(
            db.execute(
                select(func.count()).select_from(CaseContact).where(CaseContact.contact_id == survivor_id)
            ).scalar_one()
        ),
        source_matter_links=int(
            db.execute(
                select(func.count()).select_from(CaseContact).where(CaseContact.contact_id == source_id)
            ).scalar_one()
        ),
        survivor_grants=int(
            db.execute(
                select(func.count())
                .select_from(ContactPortalGrant)
                .where(ContactPortalGrant.contact_id == survivor_id)
            ).scalar_one()
        ),
        source_grants=int(
            db.execute(
                select(func.count())
                .select_from(ContactPortalGrant)
                .where(ContactPortalGrant.contact_id == source_id)
            ).scalar_one()
        ),
        survivor_client_portal_active=survivor_portal,
        source_client_portal_active=source_portal,
        survivor_matter_portal_active=len(survivor_matter_cases),
        source_matter_portal_active=len(source_matter_cases),
        email_mismatch=email_mismatch,
        type_mismatch=survivor.type != source.type,
        will_reset_client_portal=survivor_portal or source_portal,
        will_reset_matter_portal_cases=len(matter_cases_to_reset),
    )


def _uuid_key(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, uuid.UUID):
        return value.hex
    return str(value).replace("-", "").lower()


def _repoint(db: Session, model, column, *, source_id: uuid.UUID, survivor_id: uuid.UUID) -> int:
    table_name = getattr(model, "__tablename__", None)
    if table_name and not _has_table(db, table_name):
        return 0
    rows = list(db.execute(select(model).where(column == source_id)).scalars().all())
    if not rows:
        # SQLite may store UUID PKs/FKs as 32-char hex; fall back to Python-side match.
        source_key = _uuid_key(source_id)
        rows = [
            row
            for row in db.execute(select(model)).scalars().all()
            if _uuid_key(getattr(row, column.key)) == source_key
        ]
    for row in rows:
        setattr(row, column.key, survivor_id)
        db.add(row)
    if rows:
        db.flush()
    return len(rows)


def _delete_row(db: Session, model, row: object) -> None:
    """Delete a row even when SQLite stored UUID PKs as 32-char hex."""
    table_name = model.__tablename__
    pk_col = list(model.__table__.primary_key.columns)[0]
    pk = getattr(row, pk_col.name)
    from sqlalchemy import text as sa_text

    db.execute(
        sa_text(
            f"DELETE FROM {table_name} WHERE replace(lower(cast({pk_col.name} as text)), '-', '') = :pk_hex"
        ),
        {"pk_hex": _uuid_key(pk)},
    )
    if row in db:
        db.expunge(row)


def _rows_for_contact(db: Session, model, column, contact_id: uuid.UUID) -> list:
    rows = list(db.execute(select(model).where(column == contact_id)).scalars().all())
    if rows:
        return rows
    key = _uuid_key(contact_id)
    return [
        row
        for row in db.execute(select(model)).scalars().all()
        if _uuid_key(getattr(row, column.key)) == key
    ]


def _merge_grants(
    db: Session,
    *,
    source_id: uuid.UUID,
    survivor_id: uuid.UUID,
) -> tuple[int, int]:
    """Move source grants onto survivor; dedupe identical case+folder. Returns (moved, deduped)."""
    survivor_grants = _rows_for_contact(db, ContactPortalGrant, ContactPortalGrant.contact_id, survivor_id)
    source_grants = _rows_for_contact(db, ContactPortalGrant, ContactPortalGrant.contact_id, source_id)

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
                    select(ContactPortalGrantView).where(
                        ContactPortalGrantView.grant_id == grant.id,
                    )
                ).scalars().all():
                    _delete_row(db, ContactPortalGrantView, view)
            grant.contact_id = survivor_id
            db.add(grant)
            by_key[key] = grant
            moved += 1
    db.flush()
    return moved, deduped


def _merge_matter_portal(
    db: Session,
    *,
    source_id: uuid.UUID,
    survivor_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> int:
    """
    Collapse matter portal rows onto the survivor and issue fresh codes for every
    case that had access on either contact. Returns cases reset count.
    """
    source_rows = _rows_for_contact(db, MatterPortalAccess, MatterPortalAccess.contact_id, source_id)
    survivor_rows = _rows_for_contact(db, MatterPortalAccess, MatterPortalAccess.contact_id, survivor_id)
    survivor_by_case = {_uuid_key(r.case_id): r for r in survivor_rows}
    cases_needing_reset: set[str] = set(survivor_by_case.keys())

    for row in source_rows:
        case_key = _uuid_key(row.case_id)
        cases_needing_reset.add(case_key)
        existing = survivor_by_case.get(case_key)
        if existing is not None:
            _delete_row(db, MatterPortalAccess, row)
        else:
            row.contact_id = survivor_id
            db.add(row)
            survivor_by_case[case_key] = row
    db.flush()

    for case_key in cases_needing_reset:
        row = survivor_by_case.get(case_key)
        if row is None:
            continue
        code = allocate_unique_access_code(db)
        store_matter_portal_access_code(row, code)
        row.enabled = True
        row.failed_attempts = 0
        row.locked_until = None
        row.updated_at = utcnow()
        db.add(row)
    db.flush()
    return len(cases_needing_reset)


def _reset_client_portal(
    db: Session,
    *,
    survivor_id: uuid.UUID,
    source_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    should_reset: bool,
) -> str | None:
    source_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == source_id)
    ).scalar_one_or_none()
    survivor_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == survivor_id)
    ).scalar_one_or_none()

    if source_row is not None:
        _delete_row(db, ContactPortalAccess, source_row)
        db.flush()

    if not should_reset:
        return None

    code = allocate_unique_access_code(db)
    if survivor_row is None:
        survivor_row = ContactPortalAccess(
            contact_id=survivor_id,
            enabled=True,
            created_by_user_id=actor_user_id,
        )
        db.add(survivor_row)
    store_portal_access_code(survivor_row, code)
    survivor_row.enabled = True
    survivor_row.failed_attempts = 0
    survivor_row.locked_until = None
    survivor_row.updated_at = utcnow()
    db.add(survivor_row)
    db.flush()
    db.expire(survivor_row)
    return code


def merge_contacts(
    db: Session,
    *,
    survivor_id: uuid.UUID,
    source_id: uuid.UUID,
    actor: User,
) -> ContactMergeResult:
    preview = preview_contact_merge(db, survivor_id=survivor_id, source_id=source_id)
    survivor = preview.survivor
    source = preview.source

    # Drop source OTPs (cannot usefully transfer one-time codes).
    if _has_table(db, PortalLoginOtp.__tablename__):
        for otp in db.execute(select(PortalLoginOtp).where(PortalLoginOtp.contact_id == source_id)).scalars().all():
            db.delete(otp)

    # Grant views keyed by source contact (any remaining after grant merge cleanup).
    if _has_table(db, ContactPortalGrantView.__tablename__):
        for view in db.execute(
            select(ContactPortalGrantView).where(ContactPortalGrantView.contact_id == source_id)
        ).scalars().all():
            db.delete(view)
    db.flush()

    grants_moved, grants_deduped = _merge_grants(db, source_id=source_id, survivor_id=survivor_id)
    matter_cases_reset = _merge_matter_portal(
        db, source_id=source_id, survivor_id=survivor_id, actor_user_id=actor.id
    )

    matter_links_moved = _repoint(
        db, CaseContact, CaseContact.contact_id, source_id=source_id, survivor_id=survivor_id
    )
    _repoint(db, LedgerEntry, LedgerEntry.contact_id, source_id=source_id, survivor_id=survivor_id)
    _repoint(db, CaseInvoice, CaseInvoice.contact_id, source_id=source_id, survivor_id=survivor_id)
    _repoint(
        db,
        DocusignSigningRecipient,
        DocusignSigningRecipient.contact_id,
        source_id=source_id,
        survivor_id=survivor_id,
    )
    _repoint(
        db,
        CanarySignRecipient,
        CanarySignRecipient.contact_id,
        source_id=source_id,
        survivor_id=survivor_id,
    )
    _repoint(
        db,
        PortalFormSubmission,
        PortalFormSubmission.contact_id,
        source_id=source_id,
        survivor_id=survivor_id,
    )
    _repoint(
        db,
        QuotePortalDelivery,
        QuotePortalDelivery.contact_id,
        source_id=source_id,
        survivor_id=survivor_id,
    )
    _repoint(
        db,
        PortalActivityEvent,
        PortalActivityEvent.contact_id,
        source_id=source_id,
        survivor_id=survivor_id,
    )

    new_code = _reset_client_portal(
        db,
        survivor_id=survivor_id,
        source_id=source_id,
        actor_user_id=actor.id,
        should_reset=preview.will_reset_client_portal,
    )

    source_name = source.name
    source_email = source.email
    source_pk = source.id
    # Core delete avoids ORM FK sync rewriting re-pointed child rows on SQLite.
    db.expunge(source)
    db.execute(delete(Contact).where(Contact.id == source_pk))
    survivor.updated_at = utcnow()
    db.add(survivor)

    log_event(
        db,
        actor_user_id=actor.id,
        action="contact.merge",
        entity_type="contact",
        entity_id=str(survivor_id),
        meta={
            "source_contact_id": str(source_pk),
            "source_name": source_name,
            "source_email": source_email,
            "client_portal_reset": bool(new_code),
            "matter_portal_cases_reset": matter_cases_reset,
            "grants_moved": grants_moved,
            "grants_deduped": grants_deduped,
            "matter_links_moved": matter_links_moved,
        },
    )
    db.flush()
    # Drop identity-map state so a later commit cannot rewrite Core UPDATEs with stale ORM values.
    db.expire_all()
    db.commit()
    survivor = db.get(Contact, survivor_id)
    assert survivor is not None

    return ContactMergeResult(
        survivor=survivor,
        deleted_source_id=source_pk,
        client_portal_reset=bool(new_code),
        new_client_access_code=new_code,
        matter_portal_cases_reset=matter_cases_reset,
        grants_moved=grants_moved,
        grants_deduped=grants_deduped,
        matter_links_moved=matter_links_moved,
    )
