#!/usr/bin/env python3
"""Ensure staff + one Purchase matter for firm contract smoke (Phase 7).

Idempotent. Safe on a populated demo DB.

  docker compose exec backend python scripts/ensure_firm_contract_fixture.py
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    Case,
    CaseReferenceCounter,
    CaseStatus,
    MatterHeadType,
    MatterSubType,
    User,
    UserRole,
)
from app.security import hash_password

CASE_NUMBER = os.getenv("FIRM_CONTRACT_CASE_NUMBER", "900001").strip().zfill(6)
STAFF_EMAIL = os.getenv("FIRM_CONTRACT_STAFF_EMAIL", "firm.contract@example.com").strip().lower()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_staff(db) -> User:
    user = db.execute(select(User).where(User.email == STAFF_EMAIL)).scalar_one_or_none()
    if user is not None:
        return user
    user = db.execute(
        select(User).where(User.role == UserRole.admin, User.is_active.is_(True)).order_by(User.created_at.asc())
    ).scalars().first()
    if user is not None:
        return user

    now = _utcnow()
    initials = "FCI"
    clash = db.execute(select(User).where(User.initials == initials)).scalar_one_or_none()
    if clash is not None:
        initials = "F" + uuid.uuid4().hex[:3].upper()
    user = User(
        id=uuid.uuid4(),
        email=STAFF_EMAIL,
        password_hash=hash_password(os.getenv("FIRM_CONTRACT_STAFF_PASSWORD", "FirmContract!ChangeMe")),
        display_name="Firm Contract Admin",
        initials=initials,
        role=UserRole.admin,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    print(f"  + created staff admin {user.email}")
    return user


def _purchase_sub_type(db) -> MatterSubType | None:
    sub = db.execute(
        select(MatterSubType)
        .join(MatterHeadType, MatterSubType.head_type_id == MatterHeadType.id)
        .where(MatterHeadType.name == "Conveyancing, Residential", MatterSubType.name == "Purchase")
    ).scalar_one_or_none()
    if sub is not None:
        return sub
    sub = db.execute(select(MatterSubType).where(MatterSubType.name == "Purchase")).scalars().first()
    if sub is not None:
        return sub

    now = _utcnow()
    head = db.execute(
        select(MatterHeadType).where(MatterHeadType.name == "Conveyancing, Residential")
    ).scalar_one_or_none()
    if head is None:
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
        portal_enabled_default=True,
        created_at=now,
        updated_at=now,
    )
    db.add(sub)
    db.flush()
    print("  + created matter types Conveyancing, Residential → Purchase")
    return sub


def _ensure_purchase_case(db, staff: User) -> Case:
    sub = _purchase_sub_type(db)
    if sub is None:
        raise RuntimeError(
            "No Purchase matter_sub_type in catalogue (need Conveyancing, Residential → Purchase)"
        )

    existing = db.execute(
        select(Case).where(Case.matter_sub_type_id == sub.id).order_by(Case.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  = reuse Purchase matter {existing.case_number}")
        return existing

    case = db.execute(select(Case).where(Case.case_number == CASE_NUMBER)).scalar_one_or_none()
    if case is not None:
        case.matter_head_type_id = sub.head_type_id
        case.matter_sub_type_id = sub.id
        case.updated_at = _utcnow()
        db.add(case)
        print(f"  = retargeted matter {case.case_number} to Purchase")
        return case

    now = _utcnow()
    case = Case(
        id=uuid.uuid4(),
        case_number=CASE_NUMBER,
        title="Firm contract Purchase fixture",
        client_name="Firm Contract Client",
        fee_earner_user_id=staff.id,
        created_by=staff.id,
        status=CaseStatus.open,
        matter_head_type_id=sub.head_type_id,
        matter_sub_type_id=sub.id,
        created_at=now,
        updated_at=now,
    )
    db.add(case)
    db.flush()

    counter = db.execute(select(CaseReferenceCounter).where(CaseReferenceCounter.id == 1)).scalar_one_or_none()
    if counter is None:
        try:
            next_val = int(CASE_NUMBER) + 1
        except ValueError:
            next_val = 900002
        db.add(CaseReferenceCounter(id=1, next_value=next_val))
    print(f"  + created Purchase matter {case.case_number}")
    return case


def main() -> int:
    print("Ensuring firm contract fixture…")
    db = SessionLocal()
    try:
        staff = _ensure_staff(db)
        print(f"  staff={staff.email}")
        case = _ensure_purchase_case(db, staff)
        db.commit()
        print(f"OK case={case.case_number} id={case.id}")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
