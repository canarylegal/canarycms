"""Resolve contact e-mail from matter snapshot vs global card."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Case, CaseContact, CaseStatus, Contact, ContactType, User
from app.portal_service import resolve_matter_contact_email


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    try:
        for table in (User.__table__, Case.__table__, Contact.__table__, CaseContact.__table__):
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _seed_case_with_contact(
    db: Session,
    *,
    snapshot_email: str | None,
    global_email: str | None,
) -> tuple[Case, Contact]:
    uid = uuid.uuid4()
    user = User(
        id=uid,
        email=f"fee-{uid.hex[:6]}@example.com",
        password_hash="x",
        display_name="Fee Earner",
        initials="FE",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    case = Case(
        id=uuid.uuid4(),
        case_number="000001",
        title="Test matter",
        fee_earner_user_id=uid,
        created_by=uid,
        status=CaseStatus.open,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    contact = Contact(
        id=uuid.uuid4(),
        type=ContactType.person,
        name="Jane Client",
        email=global_email,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.add(case)
    db.add(contact)
    db.add(
        CaseContact(
            id=uuid.uuid4(),
            case_id=case.id,
            contact_id=contact.id,
            is_linked_to_master=True,
            type=ContactType.person,
            name="Jane Client",
            email=snapshot_email,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()
    return case, contact


def test_resolve_matter_contact_email_prefers_snapshot() -> None:
    db = _session()
    case, contact = _seed_case_with_contact(db, snapshot_email="jane@example.com", global_email=None)
    assert resolve_matter_contact_email(db, case_id=case.id, contact_id=contact.id) == "jane@example.com"


def test_resolve_matter_contact_email_falls_back_to_global() -> None:
    db = _session()
    case, contact = _seed_case_with_contact(db, snapshot_email=None, global_email="global@example.com")
    assert resolve_matter_contact_email(db, case_id=case.id, contact_id=contact.id) == "global@example.com"
