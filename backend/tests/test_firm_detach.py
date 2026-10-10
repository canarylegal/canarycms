"""Firm catalogue detach preflight / force."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.firm_detach import collect_detach_blockers, force_detach, preflight_detach
from app.models import (
    Base,
    Case,
    CaseStatus,
    FirmSettings,
    MatterHeadType,
    MatterSubType,
    User,
    UserRole,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            FirmSettings.__table__,
            MatterHeadType.__table__,
            MatterSubType.__table__,
            Case.__table__,
        ],
    )
    for column, original in patched:
        column.type = original
    return sessionmaker(bind=engine)()


def test_preflight_blocks_when_case_has_matter_type() -> None:
    db = _session()
    now = datetime.now(timezone.utc)
    admin = User(
        id=uuid.uuid4(),
        email="detach.admin@example.com",
        password_hash="x",
        display_name="Detach Admin",
        initials="DA",
        role=UserRole.admin,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(admin)
    head = MatterHeadType(id=uuid.uuid4(), name="Head", is_hidden=False, created_at=now, updated_at=now)
    db.add(head)
    db.flush()
    sub = MatterSubType(
        id=uuid.uuid4(),
        head_type_id=head.id,
        name="Purchase",
        created_at=now,
        updated_at=now,
    )
    db.add(sub)
    db.flush()
    db.add(
        Case(
            id=uuid.uuid4(),
            case_number="000001",
            title="Typed",
            fee_earner_user_id=admin.id,
            status=CaseStatus.open,
            matter_head_type_id=head.id,
            matter_sub_type_id=sub.id,
            created_by=admin.id,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()

    blockers = collect_detach_blockers(db)
    assert blockers.typed_cases == 1
    assert blockers.blocked
    result = preflight_detach(db)
    assert result.ok is False


def test_force_detach_requires_confirm() -> None:
    db = _session()
    result = force_detach(db, confirm=False)
    assert result.ok is False
    assert "confirm" in result.message.lower() or "I_CONFIRM" in result.message


def test_force_detach_clears_matter_types() -> None:
    db = _session()
    now = datetime.now(timezone.utc)
    admin = User(
        id=uuid.uuid4(),
        email="detach.force@example.com",
        password_hash="x",
        display_name="Force Admin",
        initials="FA",
        role=UserRole.admin,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(admin)
    db.add(FirmSettings(id=1, trading_name="Rhodes & Walker", updated_at=now))
    head = MatterHeadType(id=uuid.uuid4(), name="Head", is_hidden=False, created_at=now, updated_at=now)
    db.add(head)
    db.flush()
    sub = MatterSubType(
        id=uuid.uuid4(),
        head_type_id=head.id,
        name="Purchase",
        created_at=now,
        updated_at=now,
    )
    db.add(sub)
    db.flush()
    case_id = uuid.uuid4()
    db.add(
        Case(
            id=case_id,
            case_number="000002",
            title="Typed",
            fee_earner_user_id=admin.id,
            status=CaseStatus.open,
            matter_head_type_id=head.id,
            matter_sub_type_id=sub.id,
            created_by=admin.id,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()

    result = force_detach(db, confirm=True)
    assert result.ok is True
    assert result.forced is True
    db.expire_all()
    case = db.get(Case, case_id)
    assert case is not None
    assert case.matter_head_type_id is None
    assert case.matter_sub_type_id is None
    assert db.execute(text("SELECT count(*) FROM matter_head_type")).scalar() == 0
    firm = db.get(FirmSettings, 1)
    assert firm is not None
    assert firm.trading_name == "Canary"
