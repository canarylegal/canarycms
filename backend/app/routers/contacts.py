import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.contact_merge_service import merge_contacts, preview_contact_merge
from app.contact_validation import ensure_organisation_trading_name
from app.db import get_db
from app.deps import get_current_user
from app.list_search import reject_search_nul, search_contacts
from app.models import Contact, ContactType, User
from app.schemas import (
    ContactCreate,
    ContactMergeIn,
    ContactMergeOut,
    ContactMergePreviewOut,
    ContactOut,
    ContactUpdate,
)


router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactOut:
    contact = Contact(**payload.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return ContactOut.model_validate(contact, from_attributes=True)


@router.get("", response_model=list[ContactOut])
def list_contacts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, description="Search name, email, phone, address fields"),
    limit: int | None = Query(default=None, ge=1, le=200),
    type: ContactType | None = Query(default=None, alias="type"),
    has_email: bool | None = Query(default=None),
    has_phone: bool | None = Query(default=None),
) -> list[ContactOut]:
    reject_search_nul(q)
    rows = search_contacts(
        db,
        q=q,
        limit=limit,
        type_filter=type,
        has_email=has_email,
        has_phone=has_phone,
    )
    return [ContactOut.model_validate(c, from_attributes=True) for c in rows]


@router.get("/{contact_id}", response_model=ContactOut)
def get_contact(
    contact_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactOut:
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return ContactOut.model_validate(contact, from_attributes=True)


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactOut:
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(contact, key, value)
    ensure_organisation_trading_name(contact.type, contact.trading_name)
    contact.updated_at = datetime.utcnow()

    db.add(contact)
    db.commit()
    db.refresh(contact)
    return ContactOut.model_validate(contact, from_attributes=True)


@router.get("/{contact_id}/merge-preview", response_model=ContactMergePreviewOut)
def get_contact_merge_preview(
    contact_id: uuid.UUID,
    source_contact_id: uuid.UUID = Query(..., description="Duplicate contact to absorb"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactMergePreviewOut:
    preview = preview_contact_merge(db, survivor_id=contact_id, source_id=source_contact_id)
    return ContactMergePreviewOut(
        survivor=ContactOut.model_validate(preview.survivor, from_attributes=True),
        source=ContactOut.model_validate(preview.source, from_attributes=True),
        survivor_matter_links=preview.survivor_matter_links,
        source_matter_links=preview.source_matter_links,
        survivor_grants=preview.survivor_grants,
        source_grants=preview.source_grants,
        survivor_client_portal_active=preview.survivor_client_portal_active,
        source_client_portal_active=preview.source_client_portal_active,
        survivor_matter_portal_active=preview.survivor_matter_portal_active,
        source_matter_portal_active=preview.source_matter_portal_active,
        email_mismatch=preview.email_mismatch,
        type_mismatch=preview.type_mismatch,
        will_reset_client_portal=preview.will_reset_client_portal,
        will_reset_matter_portal_cases=preview.will_reset_matter_portal_cases,
    )


@router.post("/{contact_id}/merge", response_model=ContactMergeOut)
def post_contact_merge(
    contact_id: uuid.UUID,
    payload: ContactMergeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactMergeOut:
    result = merge_contacts(
        db,
        survivor_id=contact_id,
        source_id=payload.source_contact_id,
        actor=user,
    )
    email_sent = False
    email_skip_reason: str | None = None
    if payload.send_email and result.new_client_access_code:
        from app.routers.contact_portal import _notify_portal_access_email

        email_sent, email_skip_reason = _notify_portal_access_email(
            db,
            result.survivor,
            result.new_client_access_code,
            actor_user_id=user.id,
        )
        if email_sent:
            db.commit()
    return ContactMergeOut(
        survivor=ContactOut.model_validate(result.survivor, from_attributes=True),
        deleted_source_id=result.deleted_source_id,
        client_portal_reset=result.client_portal_reset,
        new_client_access_code=result.new_client_access_code,
        matter_portal_cases_reset=result.matter_portal_cases_reset,
        grants_moved=result.grants_moved,
        grants_deduped=result.grants_deduped,
        matter_links_moved=result.matter_links_moved,
        email_sent=email_sent,
        email_skip_reason=email_skip_reason,
    )


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(
    contact_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    db.delete(contact)
    log_event(
        db,
        actor_user_id=user.id,
        action="contact.delete",
        entity_type="contact",
        entity_id=str(contact_id),
        meta={},
    )
    db.commit()

