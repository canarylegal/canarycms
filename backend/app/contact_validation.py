"""Rules shared by global contacts and case-contact snapshots."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.models import ContactType


def ensure_organisation_trading_name(contact_type: ContactType, trading_name: str | None) -> None:
    if contact_type != ContactType.organisation:
        return
    if not (trading_name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Trading name is required for organisation contacts.",
        )
