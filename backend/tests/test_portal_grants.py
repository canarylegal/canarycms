"""Portal grant lifecycle and upload folder scope checks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Base,
    Case,
    CaseStatus,
    Contact,
    ContactPortalGrant,
    ContactType,
    User,
)
from app.portal_service import (
    ensure_upload_folder_allowed,
    grant_is_active,
    rename_portal_grants_for_folder,
    revoke_portal_grants_for_deleted_folder,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    try:
        for table in (User.__table__, Case.__table__, Contact.__table__, ContactPortalGrant.__table__):
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _seed(db: Session) -> tuple[Case, Contact, User]:
    uid = uuid.uuid4()
    user = User(
        id=uid,
        email=f"fee-{uid.hex[:6]}@example.com",
        password_hash="x",
        display_name="Fee Earner",
        initials=f"F{uid.hex[:3].upper()}",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    case = Case(
        id=uuid.uuid4(),
        case_number="000101",
        title="Grant matter",
        fee_earner_user_id=uid,
        created_by=uid,
        status=CaseStatus.open,
        portal_enabled=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    contact = Contact(
        id=uuid.uuid4(),
        type=ContactType.person,
        name="Client",
        email="client@example.com",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add_all([user, case, contact])
    db.commit()
    return case, contact, user


def _add_grant(
    db: Session,
    *,
    case: Case,
    contact: Contact,
    user: User,
    folder_path: str,
    label: str | None = None,
    expires_at: datetime | None = None,
    can_upload: bool = True,
) -> ContactPortalGrant:
    grant = ContactPortalGrant(
        id=uuid.uuid4(),
        contact_id=contact.id,
        case_id=case.id,
        folder_path=folder_path,
        label=label,
        can_download=True,
        can_upload=can_upload,
        expires_at=expires_at,
        created_by_user_id=user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant


def test_ensure_upload_folder_allowed_rejects_sibling_with_403() -> None:
    grant = SimpleNamespace(folder_path="shared", can_upload=True)
    with pytest.raises(HTTPException) as ei:
        ensure_upload_folder_allowed(grant=grant, folder="other")  # type: ignore[arg-type]
    assert ei.value.status_code == 403
    assert "outside this area" in str(ei.value.detail)


def test_ensure_upload_folder_allowed_rejects_sibling_prefix_trick() -> None:
    grant = SimpleNamespace(folder_path="shared", can_upload=True)
    with pytest.raises(HTTPException) as ei:
        ensure_upload_folder_allowed(grant=grant, folder="shared-extra")  # type: ignore[arg-type]
    assert ei.value.status_code == 403


def test_ensure_upload_folder_allowed_rejects_when_upload_disabled() -> None:
    grant = SimpleNamespace(folder_path="shared", can_upload=False)
    with pytest.raises(HTTPException) as ei:
        ensure_upload_folder_allowed(grant=grant, folder="shared")  # type: ignore[arg-type]
    assert ei.value.status_code == 403


def test_grant_is_active_without_expiry() -> None:
    grant = SimpleNamespace(expires_at=None)
    assert grant_is_active(grant) is True  # type: ignore[arg-type]


def test_grant_is_active_false_when_expired() -> None:
    now = datetime.now(timezone.utc)
    grant = SimpleNamespace(expires_at=now - timedelta(seconds=1))
    assert grant_is_active(grant, now=now) is False  # type: ignore[arg-type]


def test_grant_is_active_true_before_expiry() -> None:
    now = datetime.now(timezone.utc)
    grant = SimpleNamespace(expires_at=now + timedelta(hours=1))
    assert grant_is_active(grant, now=now) is True  # type: ignore[arg-type]


def test_revoke_portal_grants_for_deleted_folder_exact_and_nested() -> None:
    db = _session()
    case, contact, user = _seed(db)
    keep = _add_grant(db, case=case, contact=contact, user=user, folder_path="keep-me")
    _add_grant(db, case=case, contact=contact, user=user, folder_path="shared")
    _add_grant(db, case=case, contact=contact, user=user, folder_path="shared/inbox")
    removed = revoke_portal_grants_for_deleted_folder(db, case_id=case.id, folder_path="shared")
    db.commit()
    assert removed == 2
    remaining = db.execute(select(ContactPortalGrant)).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].id == keep.id


def test_revoke_portal_grants_empty_prefix_is_noop() -> None:
    db = _session()
    case, contact, user = _seed(db)
    _add_grant(db, case=case, contact=contact, user=user, folder_path="shared")
    assert revoke_portal_grants_for_deleted_folder(db, case_id=case.id, folder_path="") == 0


def test_rename_portal_grants_for_folder_updates_paths_and_label() -> None:
    db = _session()
    case, contact, user = _seed(db)
    exact = _add_grant(db, case=case, contact=contact, user=user, folder_path="old-name", label="old-name")
    nested = _add_grant(db, case=case, contact=contact, user=user, folder_path="old-name/docs", label="Custom")
    other = _add_grant(db, case=case, contact=contact, user=user, folder_path="elsewhere")
    updated = rename_portal_grants_for_folder(
        db,
        case_id=case.id,
        old_folder_path="old-name",
        new_folder_path="new-name",
    )
    db.commit()
    assert updated == 2
    db.refresh(exact)
    db.refresh(nested)
    db.refresh(other)
    assert exact.folder_path == "new-name"
    assert exact.label == "new-name"
    assert nested.folder_path == "new-name/docs"
    assert nested.label == "Custom"
    assert other.folder_path == "elsewhere"
