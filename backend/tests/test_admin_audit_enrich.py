"""Tests for admin audit matter enrichment on legacy rows."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.models import AuditEvent, Base, Case, CaseAccessRule, CaseContact, CaseNote, CaseTask, ContactType, File, FileCategory
from app.routers.admin_audit import _batch_resolve_case_ids, _case_id_filter, _serialize_events


def _patch_jsonb_columns_for_sqlite() -> list[tuple[object, object]]:
    """SQLite tests: temporarily map JSONB columns to JSON."""
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    return patched


def _restore_jsonb_columns(patched: list[tuple[object, object]]) -> None:
    for column, original in patched:
        column.type = original


def _audit_tables():
    return (
        Case.__table__,
        File.__table__,
        CaseContact.__table__,
        CaseTask.__table__,
        CaseNote.__table__,
        CaseAccessRule.__table__,
        AuditEvent.__table__,
    )


def _session(*tables) -> Session:
    if not tables:
        tables = _audit_tables()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched = _patch_jsonb_columns_for_sqlite()
    try:
        for table in tables:
            table.create(engine)
    finally:
        _restore_jsonb_columns(patched)
    return sessionmaker(bind=engine)()


def _case(db: Session, *, case_number: str = "100/2024") -> Case:
    case_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    row = Case(
        id=case_id,
        case_number=case_number,
        title="Test matter",
        fee_earner_user_id=actor_id,
        created_by=actor_id,
    )
    db.add(row)
    db.commit()
    return row


def test_batch_resolve_case_id_from_file_without_meta() -> None:
    db = _session(Case.__table__, File.__table__)
    case = _case(db)
    file_id = uuid.uuid4()
    db.add(
        File(
            id=file_id,
            case_id=case.id,
            owner_id=case.created_by,
            category=FileCategory.case_document,
            storage_path="/tmp/x",
            original_filename="Letter.pdf",
            mime_type="application/pdf",
            size_bytes=1,
        )
    )
    db.commit()

    event = AuditEvent(
        action="case.file.delete",
        entity_type="file",
        entity_id=str(file_id),
        meta_json=None,
        created_at=datetime.utcnow(),
    )
    resolved = _batch_resolve_case_ids(db, [event], [None])
    assert resolved == [str(case.id)]


def test_batch_resolve_case_id_from_case_contact_without_meta() -> None:
    db = _session(Case.__table__, CaseContact.__table__)
    case = _case(db, case_number="200/2024")
    cc_id = uuid.uuid4()
    db.add(
        CaseContact(
            id=cc_id,
            case_id=case.id,
            type=ContactType.person,
            name="Bob",
        )
    )
    db.commit()

    event = AuditEvent(
        action="case.contact.snapshot.create",
        entity_type="case_contact",
        entity_id=str(cc_id),
        meta_json=None,
        created_at=datetime.utcnow(),
    )
    resolved = _batch_resolve_case_ids(db, [event], [None])
    assert resolved == [str(case.id)]


def test_serialize_events_populates_matter_columns_for_legacy_file_row() -> None:
    db = _session(Case.__table__, File.__table__)
    case = _case(db, case_number="847/2024")
    file_id = uuid.uuid4()
    db.add(
        File(
            id=file_id,
            case_id=case.id,
            owner_id=case.created_by,
            category=FileCategory.case_document,
            storage_path="/tmp/y",
            original_filename="Old.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=2,
        )
    )
    db.commit()

    event = AuditEvent(
        id=uuid.uuid4(),
        action="case.file.rename",
        entity_type="file",
        entity_id=str(file_id),
        meta_json='{"old_filename":"Old.docx","new_filename":"New.docx"}',
        created_at=datetime.utcnow(),
    )
    out = _serialize_events(db, [event])
    assert len(out) == 1
    assert out[0].case_id == str(case.id)
    assert out[0].case_number == "847/2024"
    assert out[0].case_title == "Test matter"


def test_case_id_filter_matches_legacy_file_row() -> None:
    db = _session()
    case = _case(db)
    file_id = uuid.uuid4()
    db.add(
        File(
            id=file_id,
            case_id=case.id,
            owner_id=case.created_by,
            category=FileCategory.case_document,
            storage_path="/tmp/z",
            original_filename="x.pdf",
            mime_type="application/pdf",
            size_bytes=1,
        )
    )
    event = AuditEvent(
        action="case.file.upload",
        entity_type="file",
        entity_id=str(file_id),
        meta_json=None,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    db.commit()

    rows = db.execute(select(AuditEvent).where(_case_id_filter(db, case.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == event.id
