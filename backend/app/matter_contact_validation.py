"""Validation for matter contact types and lawyer–client links."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.matter_contact_constants import LAWYERS_SLUG, normalize_matter_contact_type_slug
from app.models import CaseContact, ContactType


def ensure_lawyer_contact_is_organisation(
    matter_contact_type: str | None,
    snapshot_type: ContactType | None,
) -> None:
    """Lawyers matter contacts must use organisation contact type (not individual)."""
    if normalize_matter_contact_type_slug(matter_contact_type) != LAWYERS_SLUG:
        return
    if snapshot_type != ContactType.organisation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lawyers matter contacts must be organisation type, not individual.",
        )


def normalize_and_validate_lawyer_client_ids(
    db: Session,
    case_id: uuid.UUID,
    matter_contact_type: str | None,
    lawyer_client_ids: list[uuid.UUID] | None,
    *,
    existing: CaseContact | None = None,
) -> list[str]:
    """Return JSON-safe list of linked CaseContact id strings (max 4, unique).

    For non-lawyer types, returns [] and clears links. For lawyers, enforces at least one link.
    """
    sl = normalize_matter_contact_type_slug(matter_contact_type)
    if sl != LAWYERS_SLUG:
        return []

    raw = lawyer_client_ids
    if raw is None and existing is not None:
        raw = [uuid.UUID(str(x)) for x in (existing.lawyer_client_ids or [])]
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lawyer contacts must be linked to at least one other matter contact.",
        )

    seen: set[uuid.UUID] = set()
    ordered: list[uuid.UUID] = []
    for x in raw:
        if x in seen:
            continue
        seen.add(x)
        ordered.append(x)
        if len(ordered) > 4:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A lawyer contact can link to at most four matter contacts.",
            )

    for cid in ordered:
        cc = db.get(CaseContact, cid)
        if not cc or cc.case_id != case_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid linked contact for this matter.",
            )
        if existing is not None and cc.id == existing.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A lawyer contact cannot be linked to itself.",
            )

    return [str(x) for x in ordered]
