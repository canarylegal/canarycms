import json
import uuid
from datetime import date
from io import BytesIO
from zipfile import ZipFile
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app import financial_report_snapshots as archive
from app.models import (
    FinancialReportSnapshot,
    AuditEvent,
    UserRole,
    CaseLockMode,
    ReconciliationStatus,
)
from app.reconciliation_service import create_reconciliation, approve_reconciliation
from app.period_reopening import preview_reopening, reopen_period
from tests.test_ledger_operations import fixture as ledger_fixture, post


def fixture(db=None):
    db, user, matter, other = ledger_fixture(db)
    post(db, user, matter)
    db.commit()
    row = create_reconciliation(
        db,
        actor=user,
        period_end_date=date(2098, 1, 31),
        bank_statement_balance_pence=10000,
        notes="Reviewed test totals",
    )
    db.commit()
    return db, user, matter, row


def approve(db, user, row):
    approve_reconciliation(db, actor=user, row=row)
    db.commit()
    return archive.latest_snapshot(db, "firm", row.id)


def test_approved_report_bytes_and_labels_survive_later_changes(monkeypatch):
    from app.routers.reconciliations import download_reconciliation_report

    db, user, matter, row = fixture()
    snapshot = approve(db, user, row)
    original = bytes(snapshot.archive_bytes)
    with ZipFile(BytesIO(original)) as bundle:
        report = bundle.read("report.docx")
        data = json.loads(bundle.read("data.json"))
    assert data["ledger"][0]["case_id"] == str(matter.id)
    before_name = data["ledger"][0]["fee_earner_name"]
    matter.title = "Renamed after approval"
    user.display_name = "Later staff name"
    db.commit()

    def fail(*args, **kw):
        raise AssertionError("Archived report must never rerender")

    monkeypatch.setattr(
        "app.financial_snapshot_capture.write_client_account_reconcile_report_docx",
        fail,
    )
    response = download_reconciliation_report(row.id, user, db)
    assert (
        response.body == report
        and response.headers["x-canary-archive-state"] == "archived"
    )
    assert bytes(snapshot.archive_bytes) == original
    assert before_name != user.display_name
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "financial.snapshot.download")
        )
        == 1
    )
    db.close()


def test_reopening_preserves_old_version_and_reapproval_links_new_reason():
    db, user, _, row = fixture()
    first = approve(db, user, row)
    old = bytes(first.archive_bytes)
    preview = preview_reopening(db, row.id)
    reopen_period(
        db,
        reconciliation_id=row.id,
        actor_id=user.id,
        expected_hash=preview["preview_hash"],
        reason="Reviewed corrected statement balance",
    )
    db.commit()
    assert bytes(first.archive_bytes) == old
    row.notes = "Revised review notes"
    db.commit()
    second = approve(db, user, row)
    assert second.version == 2 and second.previous_id == first.id
    manifest = archive.verify_chain(db, second)
    assert manifest["revision_reason"] == "Reviewed corrected statement balance"
    assert manifest["previous_archive_sha256"] == first.archive_sha256
    assert archive.download_snapshot(db, first, user)[0] == old
    db.close()


@pytest.mark.parametrize("failure", ["render", "archive_audit"])
def test_archive_failure_rolls_back_approval_and_artifact(failure, monkeypatch):
    db, user, _, row = fixture()

    def fail(*args, **kw):
        raise RuntimeError("Injected archive failure")

    monkeypatch.setattr(
        archive, "render_firm_docx" if failure == "render" else "log_event", fail
    )
    with pytest.raises(RuntimeError):
        approve_reconciliation(db, actor=user, row=row)
    db.rollback()
    assert row.status == ReconciliationStatus.draft and row.approved_at is None
    assert db.scalar(select(func.count()).select_from(FinancialReportSnapshot)) == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "reconciliation.approve")
        )
        == 0
    )
    db.close()


@pytest.mark.parametrize("damage", ["bytes", "manifest", "identity", "previous"])
def test_integrity_failure_never_releases_report(damage):
    db, user, _, row = fixture()
    snapshot = approve(db, user, row)
    # SQLite permits synthetic corruption; PostgreSQL rejects updates at the database layer.
    if damage == "bytes":
        snapshot.archive_bytes = b"corrupt"
    elif damage == "manifest":
        snapshot.manifest_json = "{}"
    elif damage == "identity":
        snapshot.version = 9
    else:
        snapshot.previous_id = uuid.uuid4()
    db.commit()
    with pytest.raises(HTTPException) as error:
        archive.download_snapshot(db, snapshot, user)
    assert error.value.status_code == 409
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "financial.snapshot.integrity_failure")
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "financial.snapshot.download")
        )
        == 0
    )
    db.close()


@pytest.mark.parametrize("denial", ["inactive", "ordinary", "restricted_case"])
def test_download_authorization_rechecked_on_every_request(denial):
    from tests.ledger_test_helpers import add_user, add_cashier_category

    db, user, matter, row = fixture()
    snapshot = approve(db, user, row)
    viewer = add_user(
        db,
        role=UserRole.user,
        permission_category_id=(
            add_cashier_category(db).id if denial == "restricted_case" else None
        ),
    )
    if denial == "inactive":
        viewer.is_active = False
    if denial == "restricted_case":
        matter.lock_mode = CaseLockMode.allow_list
    db.commit()
    with pytest.raises(HTTPException) as error:
        archive.download_snapshot(db, snapshot, viewer)
    assert error.value.status_code == 403
    db.close()


def test_audit_commit_failure_returns_no_download(monkeypatch):
    db, user, _, row = fixture()
    snapshot = approve(db, user, row)

    def fail():
        raise RuntimeError("Injected commit failure")

    monkeypatch.setattr(db, "commit", fail)
    with pytest.raises(RuntimeError):
        archive.download_snapshot(db, snapshot, user)
    db.rollback()
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "financial.snapshot.download")
        )
        == 0
    )
    db.close()


def test_legacy_approval_is_not_backfilled_by_download():
    from app.routers.reconciliations import download_reconciliation_report

    db, user, _, row = fixture()
    row.status = ReconciliationStatus.approved
    from app.timeutil import utcnow

    row.approved_at = utcnow()
    row.approved_by_user_id = user.id
    db.commit()
    response = download_reconciliation_report(row.id, user, db)
    assert response.headers["x-canary-archive-state"] == "legacy-unarchived"
    assert db.scalar(select(func.count()).select_from(FinancialReportSnapshot)) == 0
    db.close()


def test_bank_archive_retry_and_reapproval():
    from app import bank_recon_service as service
    from tests.test_bank_integrity import fixture as bank_fixture, PERIOD

    db, user, _, bank, _, _, _, _ = bank_fixture()
    row = service.create_bank_reconciliation(
        db,
        actor=user,
        firm_bank_account_id=bank.id,
        period_end_date=PERIOD,
        statement_balance_pence=10000,
        notes="Reviewed bank totals",
    )
    service.approve_bank_reconciliation(
        db, actor=user, row=row, expected_version=row.version
    )
    db.commit()
    first = archive.latest_snapshot(db, "bank", row.id)
    service.approve_bank_reconciliation(
        db, actor=user, row=row, expected_version=row.version
    )
    db.commit()
    assert archive.latest_snapshot(db, "bank", row.id).id == first.id
    with ZipFile(BytesIO(first.archive_bytes)) as bundle:
        data = json.loads(bundle.read("data.json"))
        assert len(data["statements"]) == 1 and len(data["ledger"]) == 1
        assert bundle.read("report.html").startswith(b"<!doctype html>")
    service.reopen_bank_reconciliation(
        db, actor=user, row=row, expected_version=row.version, reason="Second review"
    )
    service.approve_bank_reconciliation(
        db, actor=user, row=row, expected_version=row.version
    )
    db.commit()
    second = archive.latest_snapshot(db, "bank", row.id)
    assert archive.verify_chain(db, second)["revision_reason"] == "Second review"
    assert second.previous_id == first.id and second.version == 2
    db.close()


def test_history_pagination_preserves_version_order():
    from app.routers.financial_snapshots import history

    db, user, _, row = fixture()
    first = approve(db, user, row)
    preview = preview_reopening(db, row.id)
    reopen_period(
        db,
        reconciliation_id=row.id,
        actor_id=user.id,
        expected_hash=preview["preview_hash"],
        reason="Reviewed revision",
    )
    approve(db, user, row)
    page = history("firm", row.id, None, 1, user, db)
    assert [r["version"] for r in page["items"]] == [2]
    page = history("firm", row.id, page["next_before_version"], 1, user, db)
    assert (
        page["items"][0]["snapshot_id"] == str(first.id)
        and page["next_before_version"] is None
    )
    db.close()


def test_accountant_pack_uses_exact_archived_docx(monkeypatch):
    from app.accountant_pack_service import _write_reconcile_docx

    db, user, _, row = fixture()
    snapshot = approve(db, user, row)
    with ZipFile(BytesIO(snapshot.archive_bytes)) as bundle:
        expected = bundle.read("report.docx")

    def fail(*args, **kwargs):
        raise AssertionError("Must use archived artifact")

    monkeypatch.setattr(
        "app.accountant_pack_service.write_client_account_reconcile_report_docx", fail
    )
    assert _write_reconcile_docx(row, db) == expected
    snapshot.archive_bytes = b"corrupt"
    db.commit()
    with pytest.raises(HTTPException):
        _write_reconcile_docx(row, db)
    db.close()
