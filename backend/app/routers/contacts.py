import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.contact_validation import ensure_organisation_trading_name
from app.db import get_db
from app.deps import get_current_user
from app.list_search import search_contacts
from app.models import Contact, ContactType, User
from app.schemas import ContactCreate, ContactOut, ContactUpdate


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
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="contact.delete",
        entity_type="contact",
        entity_id=str(contact_id),
        meta={},
    )

