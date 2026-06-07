"""Tests for admin audit matter filtering."""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AuditEvent,
    Base,
    Case,
    CaseAccessRule,
    CaseContact,
    CaseNote,
    CaseTask,
    ContactType,
    File,
    FileCategory,
)
from app.routers.admin_audit import _case_id_filter


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    tables = (
        Case.__table__,
        File.__table__,
        CaseContact.__table__,
        CaseTask.__table__,
        CaseNote.__table__,
        CaseAccessRule.__table__,
        AuditEvent.__table__,
    )
    try:
        for table in tables:
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def test_case_id_filter_matches_meta_entity_file_and_contact() -> None:
    db = _session()
    actor_id = uuid.uuid4()
    case_a = uuid.uuid4()
    case_b = uuid.uuid4()
    file_b = uuid.uuid4()
    contact_b = uuid.uuid4()
    db.add(
        Case(
            id=case_a,
            case_number="1001",
            title="Matter A",
            fee_earner_user_id=actor_id,
            created_by=actor_id,
        )
    )
    db.add(
        Case(
            id=case_b,
            case_number="1002",
            title="Matter B",
            fee_earner_user_id=actor_id,
            created_by=actor_id,
        )
    )
    db.add(
        File(
            id=file_b,
            case_id=case_b,
            owner_id=actor_id,
            category=FileCategory.case_document,
            storage_path="/tmp/x",
            original_filename="x.pdf",
            mime_type="application/pdf",
            size_bytes=1,
        )
    )
    db.add(
        CaseContact(
            id=contact_b,
            case_id=case_b,
            type=ContactType.person,
            name="Bob",
        )
    )
    events = [
        AuditEvent(action="case.update", entity_type="case", entity_id=str(case_a)),
        AuditEvent(
            action="case.file.upload",
            entity_type="file",
            entity_id=str(uuid.uuid4()),
            meta_json=f'{{"case_id":"{case_a}"}}',
        ),
        AuditEvent(action="case.file.delete", entity_type="file", entity_id=str(file_b)),
        AuditEvent(
            action="case.contact.snapshot.create",
            entity_type="case_contact",
            entity_id=str(contact_b),
        ),
        AuditEvent(
            action="auth.login",
            entity_type="user",
            entity_id=str(actor_id),
            meta_json='{"email":"a@example.com"}',
        ),
    ]
    db.add_all(events)
    db.commit()

    stmt = select(AuditEvent).where(_case_id_filter(db, case_a))
    matched = {e.action for e in db.execute(stmt).scalars().all()}
    assert matched == {"case.update", "case.file.upload"}

    stmt_b = select(AuditEvent).where(_case_id_filter(db, case_b))
    matched_b = {e.action for e in db.execute(stmt_b).scalars().all()}
    assert matched_b == {"case.file.delete", "case.contact.snapshot.create"}
