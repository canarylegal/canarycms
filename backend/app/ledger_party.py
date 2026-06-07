"""Resolve ledger party from optional contact references and display label."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import CaseContact, Contact
from app.schemas import LedgerPostCreate


@dataclass(frozen=True)
class ResolvedLedgerParty:
    contact_label: str | None
    case_contact_id: uuid.UUID | None
    contact_id: uuid.UUID | None


def resolve_ledger_party(case_id: uuid.UUID, payload: LedgerPostCreate, db: Session) -> ResolvedLedgerParty:
    """Validate party refs and derive the stored label snapshot."""
    cc_id = payload.case_contact_id
    global_id = payload.contact_id
    if cc_id is not None and global_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Specify either a matter contact or a global contact, not both.",
        )

    label = payload.contact_label.strip() if payload.contact_label and payload.contact_label.strip() else None

    if cc_id is not None:
        cc = db.get(CaseContact, cc_id)
        if cc is None or cc.case_id != case_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Matter contact not found on this case.",
            )
        return ResolvedLedgerParty(
            contact_label=label or cc.name,
            case_contact_id=cc_id,
            contact_id=None,
        )

    if global_id is not None:
        contact = db.get(Contact, global_id)
        if contact is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Global contact not found.",
            )
        return ResolvedLedgerParty(
            contact_label=label or contact.name,
            case_contact_id=None,
            contact_id=global_id,
        )

    return ResolvedLedgerParty(contact_label=label, case_contact_id=None, contact_id=None)
