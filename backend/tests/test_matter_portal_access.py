"""Matter-scoped portal exchange access helpers."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.matter_contact_constants import is_exchange_matter_contact_type
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
from app.portal_service import (
    ensure_matter_portal_access,
    get_matter_portal_access_by_code,
    hash_access_code,
    matter_portal_access_is_active,
    revoke_matter_portal_access_for_case,
)
from app.security import create_portal_session_token, decode_portal_session_token


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


def _seed(db: Session, *, matter_type: str = "lawyers") -> tuple[Case, Contact, User]:
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
        case_number="000099",
        title="Exchange matter",
        fee_earner_user_id=uid,
        created_by=uid,
        status=CaseStatus.open,
        portal_enabled=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    contact = Contact(
        id=uuid.uuid4(),
        type=ContactType.organisation,
        name="Other Side LLP",
        email="other@example.com",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add_all([user, case, contact])
    db.add(
        CaseContact(
            id=uuid.uuid4(),
            case_id=case.id,
            contact_id=contact.id,
            is_linked_to_master=True,
            type=ContactType.organisation,
            name="Other Side LLP",
            email="other@example.com",
            matter_contact_type=matter_type,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()
    return case, contact, user


def test_is_exchange_matter_contact_type() -> None:
    assert is_exchange_matter_contact_type("lawyers")
    assert is_exchange_matter_contact_type("new-lender")
    assert not is_exchange_matter_contact_type("client")
    assert not is_exchange_matter_contact_type("")


def test_ensure_matter_portal_access_and_lookup() -> None:
    db = _session()
    case, contact, user = _seed(db)
    row, newly, code = ensure_matter_portal_access(
        db, case_id=case.id, contact_id=contact.id, actor_user_id=user.id
    )
    db.commit()
    assert newly is True
    assert code
    assert matter_portal_access_is_active(row)
    found = get_matter_portal_access_by_code(db, code)
    assert found is not None
    assert found.id == row.id
    assert found.code_sha256 == hash_access_code(code)


def test_reject_client_matter_type_for_exchange() -> None:
    db = _session()
    case, contact, user = _seed(db, matter_type="client")
    try:
        ensure_matter_portal_access(db, case_id=case.id, contact_id=contact.id, actor_user_id=user.id)
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400


def test_exchange_session_token_claims() -> None:
    case_id = str(uuid.uuid4())
    token = create_portal_session_token(
        contact_id=str(uuid.uuid4()),
        session_version=3,
        audience="exchange",
        case_id=case_id,
    )
    payload = decode_portal_session_token(token)
    assert payload.audience == "exchange"
    assert payload.case_id == case_id
    assert payload.session_version == 3


def test_revoke_matter_portal_access_for_case() -> None:
    db = _session()
    case, contact, user = _seed(db)
    row, _, code = ensure_matter_portal_access(
        db, case_id=case.id, contact_id=contact.id, actor_user_id=user.id
    )
    db.commit()
    assert code
    n = revoke_matter_portal_access_for_case(db, case.id)
    db.commit()
    assert n == 1
    db.refresh(row)
    assert row.enabled is False
    assert not matter_portal_access_is_active(row)
