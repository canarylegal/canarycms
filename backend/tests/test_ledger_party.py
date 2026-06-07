"""Tests for ledger party contact reference resolution."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.ledger_party import resolve_ledger_party
from app.models import Base, Case, CaseContact, Contact, ContactType
from app.schemas import LedgerPostCreate


def _session(*tables) -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    try:
        for table in tables:
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _case(db: Session) -> Case:
    actor_id = uuid.uuid4()
    row = Case(
        id=uuid.uuid4(),
        case_number="100/2024",
        title="Test matter",
        fee_earner_user_id=actor_id,
        created_by=actor_id,
    )
    db.add(row)
    db.commit()
    return row


def test_resolve_matter_contact_stores_id_and_label() -> None:
    db = _session(Case.__table__, CaseContact.__table__)
    case = _case(db)
    cc_id = uuid.uuid4()
    db.add(
        CaseContact(
            id=cc_id,
            case_id=case.id,
            type=ContactType.person,
            name="Alice Client",
        )
    )
    db.commit()

    party = resolve_ledger_party(
        case.id,
        LedgerPostCreate(
            description="Receipt",
            amount_pence=1000,
            client_direction="debit",
            case_contact_id=cc_id,
        ),
        db,
    )
    assert party.case_contact_id == cc_id
    assert party.contact_id is None
    assert party.contact_label == "Alice Client"


def test_resolve_global_contact_stores_id_and_label() -> None:
    db = _session(Case.__table__, Contact.__table__)
    case = _case(db)
    contact_id = uuid.uuid4()
    db.add(
        Contact(
            id=contact_id,
            type=ContactType.organisation,
            name="Beta Ltd",
        )
    )
    db.commit()

    party = resolve_ledger_party(
        case.id,
        LedgerPostCreate(
            description="Disbursement",
            amount_pence=500,
            office_direction="debit",
            contact_id=contact_id,
        ),
        db,
    )
    assert party.contact_id == contact_id
    assert party.case_contact_id is None
    assert party.contact_label == "Beta Ltd"


def test_resolve_rejects_both_contact_ids() -> None:
    db = _session(Case.__table__)
    case = _case(db)
    with pytest.raises(HTTPException) as exc:
        resolve_ledger_party(
            case.id,
            LedgerPostCreate(
                description="X",
                amount_pence=100,
                client_direction="debit",
                case_contact_id=uuid.uuid4(),
                contact_id=uuid.uuid4(),
            ),
            db,
        )
    assert exc.value.status_code == 422


def test_resolve_rejects_matter_contact_from_other_case() -> None:
    db = _session(Case.__table__, CaseContact.__table__)
    case_a = _case(db)
    case_b = Case(
        id=uuid.uuid4(),
        case_number="200/2024",
        title="Other",
        fee_earner_user_id=case_a.created_by,
        created_by=case_a.created_by,
    )
    cc_id = uuid.uuid4()
    db.add(case_b)
    db.add(
        CaseContact(
            id=cc_id,
            case_id=case_b.id,
            type=ContactType.person,
            name="Wrong case",
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as exc:
        resolve_ledger_party(
            case_a.id,
            LedgerPostCreate(
                description="X",
                amount_pence=100,
                client_direction="debit",
                case_contact_id=cc_id,
            ),
            db,
        )
    assert exc.value.status_code == 400


def test_resolve_label_only_for_other_or_na() -> None:
    db = _session(Case.__table__)
    case = _case(db)
    party = resolve_ledger_party(
        case.id,
        LedgerPostCreate(
            description="Office fee",
            amount_pence=100,
            office_direction="debit",
            contact_label="Land Registry",
        ),
        db,
    )
    assert party.case_contact_id is None
    assert party.contact_id is None
    assert party.contact_label == "Land Registry"
