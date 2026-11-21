"""Approval archives against a disposable migrated database, including real races."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import HTTPException
from sqlalchemy import text, select, func
from sqlalchemy.exc import DBAPIError
from app.db import SessionLocal
from app.models import FinancialReportSnapshot, ClientAccountReconciliation, User
from app import financial_report_snapshots as archive
from app.reconciliation_service import approve_reconciliation
from tests.test_financial_snapshots import fixture, approve


def test_postgres_archive_is_append_only(db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("isolated PostgreSQL required")
    _, user, _, row = fixture(db)
    try:
        snapshot = approve(db, user, row)
        identity = snapshot.id
        original = bytes(snapshot.archive_bytes)
        for sql in (
            "UPDATE financial_report_snapshot SET version=version+1 WHERE id=:id",
            "DELETE FROM financial_report_snapshot WHERE id=:id",
            "TRUNCATE financial_report_snapshot CASCADE",
        ):
            with pytest.raises(DBAPIError):
                with db.begin_nested():
                    db.execute(text(sql), {"id": identity})
        assert (
            bytes(db.get(FinancialReportSnapshot, identity).archive_bytes) == original
        )
        assert archive.verify_chain(db, snapshot)["version"] == 1
    finally:
        db.delete(row)
        db.commit()


@pytest.mark.parametrize("rollback", [False, True])
def test_concurrent_approval_creates_exactly_one_archive(db, rollback):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("isolated PostgreSQL required")
    _, user, _, row = fixture(db)
    uid, rid = user.id, row.id
    db.rollback()
    locked, attempted = Event(), Event()

    def attempt(session):
        return approve_reconciliation(
            session,
            actor=session.get(User, uid),
            row=session.get(ClientAccountReconciliation, rid),
        )

    def winner():
        with SessionLocal() as session:
            attempt(session)
            locked.set()
            assert attempted.wait(15)
            session.rollback() if rollback else session.commit()

    def contender():
        assert locked.wait(15)
        try:
            with SessionLocal() as session:
                with pytest.raises(HTTPException) as error:
                    attempt(session)
                assert error.value.status_code == 409
        finally:
            attempted.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(winner), pool.submit(contender)
            a.result(20)
            b.result(20)
        if rollback:
            attempt(db)
            db.commit()
        count = db.scalar(
            select(func.count())
            .select_from(FinancialReportSnapshot)
            .where(FinancialReportSnapshot.source_id == rid)
        )
        assert count == 1
        archive.verify_chain(db, archive.latest_snapshot(db, "firm", rid))
    finally:
        db.delete(db.get(ClientAccountReconciliation, rid))
        db.commit()


def test_postgres_render_failure_keeps_draft(db, monkeypatch):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("isolated PostgreSQL required")
    _, user, _, row = fixture(db)
    rid = row.id

    def fail(*args):
        raise RuntimeError("Injected rendering failure")

    monkeypatch.setattr(archive, "render_firm_docx", fail)
    with pytest.raises(RuntimeError):
        approve_reconciliation(db, actor=user, row=row)
    db.rollback()
    assert db.get(ClientAccountReconciliation, rid).status.value == "draft"
    assert archive.latest_snapshot(db, "firm", rid) is None
    db.delete(row)
    db.commit()
