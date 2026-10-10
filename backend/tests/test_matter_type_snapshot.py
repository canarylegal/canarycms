"""Case matter-type name snapshots for firm detach / reattach."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.matter_type_snapshot import (
    capture_snapshots_before_unlink,
    restore_case_matter_types_from_snapshots,
    sync_case_matter_type_snapshot,
)
from app.models import (
    Base,
    Case,
    CaseStatus,
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
            MatterHeadType.__table__,
            MatterSubType.__table__,
            Case.__table__,
        ],
    )
    for column, original in patched:
        column.type = original
    return sessionmaker(bind=engine)()


def _seed(db: Session) -> tuple[User, MatterHeadType, MatterSubType]:
    now = datetime.now(timezone.utc)
    admin = User(
        id=uuid.uuid4(),
        email="snap@example.com",
        password_hash="x",
        display_name="Snap",
        initials="SN",
        role=UserRole.admin,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(admin)
    head = MatterHeadType(
        id=uuid.uuid4(),
        name="Conveyancing, Residential",
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )
    db.add(head)
    db.flush()
    sub = MatterSubType(
        id=uuid.uuid4(),
        head_type_id=head.id,
        name="Purchase",
        prefix="Purchase of",
        created_at=now,
        updated_at=now,
    )
    db.add(sub)
    db.flush()
    return admin, head, sub


def test_sync_and_restore_after_unlink() -> None:
    db = _session()
    now = datetime.now(timezone.utc)
    admin, head, sub = _seed(db)
    case = Case(
        id=uuid.uuid4(),
        case_number="000100",
        title="Purchase of 1 Test Street",
        fee_earner_user_id=admin.id,
        status=CaseStatus.open,
        matter_head_type_id=head.id,
        matter_sub_type_id=sub.id,
        created_by=admin.id,
        created_at=now,
        updated_at=now,
    )
    sync_case_matter_type_snapshot(case, db)
    db.add(case)
    db.commit()
    assert case.matter_head_type_name == "Conveyancing, Residential"
    assert case.matter_sub_type_name == "Purchase"

    capture_snapshots_before_unlink(db)
    case.matter_head_type_id = None
    case.matter_sub_type_id = None
    db.add(case)
    db.commit()

    # Simulate reattach with new catalogue UUIDs but same names
    db.delete(sub)
    db.delete(head)
    db.flush()
    head2 = MatterHeadType(
        id=uuid.uuid4(),
        name="Conveyancing, Residential",
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )
    db.add(head2)
    db.flush()
    sub2 = MatterSubType(
        id=uuid.uuid4(),
        head_type_id=head2.id,
        name="Purchase",
        prefix="Purchase of",
        created_at=now,
        updated_at=now,
    )
    db.add(sub2)
    db.commit()

    n = restore_case_matter_types_from_snapshots(db)
    assert n == 1
    db.refresh(case)
    assert case.matter_sub_type_id == sub2.id
    assert case.matter_head_type_id == head2.id


def test_admin_clear_clears_snapshot() -> None:
    db = _session()
    now = datetime.now(timezone.utc)
    admin, head, sub = _seed(db)
    case = Case(
        id=uuid.uuid4(),
        case_number="000101",
        title="x",
        fee_earner_user_id=admin.id,
        status=CaseStatus.open,
        matter_head_type_id=head.id,
        matter_sub_type_id=sub.id,
        created_by=admin.id,
        created_at=now,
        updated_at=now,
    )
    sync_case_matter_type_snapshot(case, db)
    case.matter_head_type_id = None
    case.matter_sub_type_id = None
    sync_case_matter_type_snapshot(case, db)
    assert case.matter_head_type_name is None
    assert case.matter_sub_type_name is None
