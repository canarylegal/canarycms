"""Shared in-memory DB helpers for ledger and invoice tests."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AuditEvent,
    Base,
    Case,
    CaseInvoice,
    CaseInvoiceLine,
    CaseStatus,
    File,
    FirmSettings,
    InvoiceSeq,
    LedgerAccount,
    LedgerEntry,
    User,
    UserPermissionCategory,
    UserRole,
)


def ledger_test_session() -> Session:
    """SQLite session with ledger, invoice, and audit tables."""
    engine = create_engine("sqlite+pysqlite:///:memory:")

    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()

    tables = (
        UserPermissionCategory.__table__,
        User.__table__,
        Case.__table__,
        LedgerAccount.__table__,
        LedgerEntry.__table__,
        InvoiceSeq.__table__,
        CaseInvoice.__table__,
        CaseInvoiceLine.__table__,
        File.__table__,
        FirmSettings.__table__,
        AuditEvent.__table__,
    )
    try:
        for table in tables:
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original

    return sessionmaker(bind=engine)()


def add_user(
    db: Session,
    *,
    role: UserRole = UserRole.admin,
    permission_category_id: uuid.UUID | None = None,
    email: str | None = None,
) -> User:
    uid = uuid.uuid4()
    row = User(
        id=uid,
        email=email or f"user-{uid.hex[:8]}@example.com",
        password_hash="x",
        display_name="Test User",
        initials=f"U{uid.hex[:4].upper()}",
        role=role,
        permission_category_id=permission_category_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_cashier_category(db: Session) -> UserPermissionCategory:
    row = UserPermissionCategory(
        id=uuid.uuid4(),
        name="Cashier",
        perm_fee_earner=False,
        perm_post_client=True,
        perm_post_office=True,
        perm_approve_payments=True,
        perm_approve_invoices=True,
        perm_admin=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_case(db: Session, *, fee_earner_user_id: uuid.UUID) -> Case:
    row = Case(
        id=uuid.uuid4(),
        case_number=f"TST/{uuid.uuid4().hex[:6]}",
        title="Ledger test matter",
        fee_earner_user_id=fee_earner_user_id,
        created_by=fee_earner_user_id,
        status=CaseStatus.open,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
