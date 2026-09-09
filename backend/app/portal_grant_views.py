"""Per-contact last-viewed timestamps for portal shared-folder grants."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.models import ContactPortalGrant, File, FileCategory
from app.portal_service import list_grant_files


class ContactPortalGrantView(Base):
    """When a portal contact last opened a shared-folder grant."""

    __tablename__ = "contact_portal_grant_view"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="CASCADE"), primary_key=True
    )
    grant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact_portal_grant.id", ondelete="CASCADE"), primary_key=True
    )
    last_viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def get_grant_last_viewed_at(db: Session, *, contact_id: uuid.UUID, grant_id: uuid.UUID) -> datetime | None:
    row = db.get(ContactPortalGrantView, {"contact_id": contact_id, "grant_id": grant_id})
    return _as_aware(row.last_viewed_at) if row else None


def mark_grant_viewed(db: Session, *, contact_id: uuid.UUID, grant_id: uuid.UUID) -> datetime:
    now = _utcnow()
    row = db.get(ContactPortalGrantView, {"contact_id": contact_id, "grant_id": grant_id})
    if row is None:
        row = ContactPortalGrantView(contact_id=contact_id, grant_id=grant_id, last_viewed_at=now)
        db.add(row)
    else:
        row.last_viewed_at = now
        db.add(row)
    db.flush()
    return now


def file_is_new_since(row: File, last_viewed_at: datetime | None) -> bool:
    """True when the contact has never viewed the grant, or the file is newer than last view."""
    created = _as_aware(row.created_at)
    if created is None:
        return False
    if last_viewed_at is None:
        return True
    return created > last_viewed_at


def count_new_files_for_grant(
    db: Session,
    grant: ContactPortalGrant,
    *,
    contact_id: uuid.UUID,
) -> int:
    last = get_grant_last_viewed_at(db, contact_id=contact_id, grant_id=grant.id)
    files = list_grant_files(db, grant)
    return sum(1 for f in files if f.category == FileCategory.case_document and file_is_new_since(f, last))


def count_new_files_in_browse(
    db: Session,
    grant: ContactPortalGrant,
    *,
    contact_id: uuid.UUID,
    files: list[File],
) -> int:
    last = get_grant_last_viewed_at(db, contact_id=contact_id, grant_id=grant.id)
    return sum(1 for f in files if file_is_new_since(f, last))
