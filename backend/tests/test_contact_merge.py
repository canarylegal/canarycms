"""Contact merge: absorb duplicate into survivor and reset portal codes."""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.contact_merge_service import merge_contacts, preview_contact_merge
from app.models import (
    AuditEvent,
    Base,
    Case,
    CaseContact,
    CaseStatus,
    Contact,
    ContactPortalAccess,
    ContactPortalGrant,
    ContactType,
    MatterPortalAccess,
    User,
)
from app.portal_service import hash_access_code, store_matter_portal_access_code, store_portal_access_code


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    try:
        for table in (
            User.__table__,
            Case.__table__,
            Contact.__table__,
            CaseContact.__table__,
            ContactPortalAccess.__table__,
            ContactPortalGrant.__table__,
            MatterPortalAccess.__table__,
            AuditEvent.__table__,
        ):
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _user(db: Session) -> User:
    uid = uuid.uuid4()
    user = User(
        id=uid,
        email=f"u-{uid.hex[:6]}@example.com",
        password_hash="x",
        display_name="Staff",
        initials="ST",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    return user


def _contact(db: Session, *, name: str, email: str) -> Contact:
    c = Contact(
        id=uuid.uuid4(),
        type=ContactType.person,
        name=name,
        email=email,
        first_name=name.split()[0],
        last_name=name.split()[-1],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(c)
    return c


def _case(db: Session, user: User) -> Case:
    case = Case(
        id=uuid.uuid4(),
        case_number="000042",
        title="Merge matter",
        fee_earner_user_id=user.id,
        created_by=user.id,
        status=CaseStatus.open,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(case)
    return case


def test_preview_flags_portal_reset_and_email_mismatch() -> None:
    db = _session()
    user = _user(db)
    survivor = _contact(db, name="Ann Lee", email="ann@example.com")
    source = _contact(db, name="Anne Lee", email="anne@example.com")
    with patch("app.email_crypt.encrypt_password", side_effect=lambda c: f"enc:{c}"):
        for contact, code in ((survivor, "AAAA-BBBB-CCCC"), (source, "DDDD-EEEE-FFFF")):
            row = ContactPortalAccess(
                id=uuid.uuid4(),
                contact_id=contact.id,
                enabled=True,
                created_by_user_id=user.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(row)
            store_portal_access_code(row, code)
        db.commit()

    preview = preview_contact_merge(db, survivor_id=survivor.id, source_id=source.id)
    assert preview.will_reset_client_portal is True
    assert preview.email_mismatch is True
    assert preview.survivor_client_portal_active is True
    assert preview.source_client_portal_active is True


def test_merge_resets_client_portal_and_deletes_source() -> None:
    db = _session()
    user = _user(db)
    survivor = _contact(db, name="Ann Lee", email="ann@example.com")
    source = _contact(db, name="Anne Lee", email="ann@example.com")
    with patch("app.email_crypt.encrypt_password", side_effect=lambda c: f"enc:{c}"):
        for contact, code in ((survivor, "AAAA-BBBB-CCCC"), (source, "DDDD-EEEE-FFFF")):
            row = ContactPortalAccess(
                id=uuid.uuid4(),
                contact_id=contact.id,
                enabled=True,
                created_by_user_id=user.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(row)
            store_portal_access_code(row, code)
        db.commit()

        with patch("app.contact_merge_service.allocate_unique_access_code", return_value="ZZZZ-YYYY-XXXX"):
            result = merge_contacts(db, survivor_id=survivor.id, source_id=source.id, actor=user)

    assert result.client_portal_reset is True
    assert result.new_client_access_code == "ZZZZ-YYYY-XXXX"
    assert db.get(Contact, source.id) is None
    db.expire_all()
    access = db.execute(select(ContactPortalAccess)).scalar_one()
    assert access.code_sha256 == hash_access_code("ZZZZ-YYYY-XXXX")
    assert (
        db.execute(
            select(ContactPortalAccess).where(ContactPortalAccess.code_sha256 == hash_access_code("AAAA-BBBB-CCCC"))
        ).scalar_one_or_none()
        is None
    )


def test_merge_moves_grant_onto_survivor() -> None:
    db = _session()
    user = _user(db)
    survivor = _contact(db, name="Ann Lee", email="ann@example.com")
    source = _contact(db, name="Ann Lee 2", email="ann@example.com")
    case = _case(db, user)
    db.add(
        ContactPortalGrant(
            id=uuid.uuid4(),
            contact_id=source.id,
            case_id=case.id,
            folder_path="Client documents",
            can_download=True,
            can_upload=False,
            created_by_user_id=user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()

    result = merge_contacts(db, survivor_id=survivor.id, source_id=source.id, actor=user)
    assert result.grants_moved == 1
    db.expire_all()
    grants = list(db.execute(select(ContactPortalGrant)).scalars().all())
    assert len(grants) == 1
    assert grants[0].folder_path == "Client documents"
