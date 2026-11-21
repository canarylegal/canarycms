"""Failure-path regressions for document creation and database-only filing."""

import uuid
from pathlib import Path
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import File, FileCategory, AuditEvent, DocumentOperation
from app.schemas import (
    CaseFileRenameUpdate,
    CaseFileMoveUpdate,
    ComposeOfficeDocumentIn,
)
from app import case_file_mutate_service as filing, file_upload_service as creation
from tests.ledger_test_helpers import ledger_test_session, add_user, add_case


def fixture(tmp_path, monkeypatch, db=None):
    db = db or ledger_test_session()
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    monkeypatch.setattr("app.file_storage.FILES_ROOT", tmp_path)
    monkeypatch.setattr(filing, "FILES_ROOT", tmp_path)
    monkeypatch.setattr(creation, "FILES_ROOT", tmp_path)
    monkeypatch.setattr(filing, "raise_if_files_checked_out", lambda *a, **kw: None)
    row = File(
        id=uuid.uuid4(),
        case_id=case.id,
        owner_id=user.id,
        category=FileCategory.case_document,
        storage_path=str(uuid.uuid4()) + ".txt",
        folder_path="",
        original_filename="original.txt",
        mime_type="text/plain",
        size_bytes=8,
        version=1,
    )
    db.add(row)
    db.commit()
    (tmp_path / row.storage_path).write_bytes(b"original")
    return db, user, case, row


@pytest.mark.parametrize("operation", ["rename", "move"])
@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_failed_filing_preserves_original_paths_and_metadata(
    tmp_path, monkeypatch, operation, failure
):
    db, user, case, row = fixture(tmp_path, monkeypatch)
    path = row.storage_path
    monkeypatch.setattr(filing, "_folder_destination_exists", lambda *a: True)

    def fail(*args, **kwargs):
        raise RuntimeError("Injected failure")

    if failure == "audit":
        monkeypatch.setattr(filing, "log_event", fail)
    else:
        monkeypatch.setattr(db, "commit", fail)
    with pytest.raises(RuntimeError):
        if operation == "rename":
            filing.rename_case_file(
                case.id,
                row.id,
                CaseFileRenameUpdate(
                    original_filename="renamed.txt",
                    expected_original_filename="original.txt",
                ),
                user,
                db,
            )
        else:
            filing.move_case_file(
                case.id, row.id, CaseFileMoveUpdate(folder_path="Destination"), user, db
            )
    assert (
        row.original_filename == "original.txt"
        and row.folder_path == ""
        and row.storage_path == path
    )
    assert (tmp_path / path).read_bytes() == b"original"
    db.close()


def test_filing_replay_does_not_repeat_or_undo_later_changes(tmp_path, monkeypatch):
    db, user, case, row = fixture(tmp_path, monkeypatch)
    db.info["document_operation_key"] = str(uuid.uuid4())
    payload = CaseFileRenameUpdate(
        original_filename="first.txt", expected_original_filename="original.txt"
    )
    response = filing.rename_case_file(case.id, row.id, payload, user, db)
    row.original_filename = "later.txt"
    db.commit()
    assert filing.rename_case_file(case.id, row.id, payload, user, db) == response
    assert row.original_filename == "later.txt"
    with pytest.raises(HTTPException):
        filing.rename_case_file(
            case.id,
            row.id,
            CaseFileRenameUpdate(
                original_filename="changed.txt", expected_original_filename="later.txt"
            ),
            user,
            db,
        )
    assert db.scalar(select(func.count()).select_from(DocumentOperation)) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "case.file.rename")
        )
        == 1
    )
    db.close()


def compose_fixture(tmp_path, monkeypatch):
    db, user, case, row = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        creation,
        "merge_compose_docx_bytes",
        lambda *a, **kw: (b"durable document", "application/test"),
    )
    monkeypatch.setattr(creation, "_prepare_upload_folder", lambda *a: "")
    db.info["document_operation_key"] = str(uuid.uuid4())
    return db, user, case, ComposeOfficeDocumentIn(original_filename="Created.docx")


def test_creation_lost_commit_response_replays_original_bytes(tmp_path, monkeypatch):
    db, user, case, payload = compose_fixture(tmp_path, monkeypatch)
    commit = db.commit

    def uncertain():
        commit()
        raise RuntimeError("Acknowledgement lost after commit")

    monkeypatch.setattr(db, "commit", uncertain)
    with pytest.raises(RuntimeError):
        creation.compose_office_document(case.id, payload, user, db)
    monkeypatch.setattr(db, "commit", commit)
    response = creation.compose_office_document(case.id, payload, user, db)
    row = db.get(File, uuid.UUID(response["id"]))
    assert (tmp_path / row.storage_path).read_bytes() == b"durable document"
    assert (
        row.checksum
        and db.scalar(select(func.count()).select_from(DocumentOperation)) == 1
    )
    db.delete(row)
    db.commit()
    with pytest.raises(HTTPException) as error:
        creation.compose_office_document(case.id, payload, user, db)
    assert error.value.status_code == 410
    db.close()


@pytest.mark.parametrize("failure", ["disk", "audit", "commit"])
def test_creation_failure_never_publishes_a_broken_record(
    tmp_path, monkeypatch, failure
):
    db, user, case, payload = compose_fixture(tmp_path, monkeypatch)
    baseline = db.scalar(select(func.count()).select_from(File))

    def fail(*a, **kw):
        raise OSError("Injected write failure")

    if failure == "disk":
        monkeypatch.setattr("app.document_durability.sync_path", fail)
    elif failure == "audit":
        monkeypatch.setattr(creation, "log_event", fail)
    else:
        monkeypatch.setattr(db, "commit", fail)
    with pytest.raises(OSError):
        creation.compose_office_document(case.id, payload, user, db)
    assert db.scalar(select(func.count()).select_from(File)) == baseline
    assert db.scalar(select(func.count()).select_from(DocumentOperation)) == 0
    db.close()


def test_invoice_render_failure_rolls_back_financial_approval(tmp_path, monkeypatch):
    from app.invoice_service import (
        create_case_invoice,
        approve_case_invoice,
        INV_PENDING,
    )
    from tests.test_invoice_service import _invoice_payload
    from app.models import CaseInvoice, LedgerEntry

    db, user, case, _ = fixture(tmp_path, monkeypatch)
    created = create_case_invoice(
        case.id, _invoice_payload(credit_user_id=user.id), user, db
    )
    db.commit()

    def fail(*a, **kw):
        raise OSError("Disk unavailable")

    monkeypatch.setattr("app.invoice_document_service.build_invoice_docx_bytes", fail)
    with pytest.raises(Exception):
        approve_case_invoice(case.id, created.id, user, db)
    db.rollback()
    inv = db.get(CaseInvoice, created.id)
    assert inv.status == INV_PENDING and inv.document_file_id is None
    assert all(
        not row.is_approved
        for row in db.scalars(
            select(LedgerEntry).where(LedgerEntry.pair_id == inv.ledger_pair_id)
        )
    )
    db.close()


def test_folder_group_failure_and_retry_preserve_bytes(tmp_path, monkeypatch):
    from app import case_folder_service as folders
    from app.schemas import CaseFolderRenameUpdate

    db, user, case, row = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr("app.file_storage.FILES_ROOT", tmp_path)
    monkeypatch.setattr(folders, "raise_if_files_checked_out", lambda *a, **kw: None)
    monkeypatch.setattr(
        "app.portal_service.rename_portal_grants_for_folder", lambda *a, **kw: None
    )
    row.folder_path = "100%/Child"
    db.commit()
    path = row.storage_path
    payload = CaseFolderRenameUpdate(old_folder_path="100%", new_folder_path="Filed")
    db.info["document_operation_key"] = str(uuid.uuid4())
    original = folders.log_event

    def fail(*a, **kw):
        raise RuntimeError("Audit failed")

    monkeypatch.setattr(folders, "log_event", fail)
    with pytest.raises(RuntimeError):
        folders.rename_case_folder(case.id, payload, user, db)
    assert (
        row.folder_path == "100%/Child"
        and (tmp_path / path).read_bytes() == b"original"
    )
    monkeypatch.setattr(folders, "log_event", original)
    response = folders.rename_case_folder(case.id, payload, user, db)
    assert row.folder_path == "Filed/Child" and row.storage_path == path
    assert folders.rename_case_folder(case.id, payload, user, db) == response
    db.close()


def test_missing_saved_invoice_is_not_silently_regenerated(tmp_path, monkeypatch):
    from app.invoice_document_service import read_invoice_document_bytes
    from types import SimpleNamespace

    db, user, case, row = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr("app.invoice_document_service.FILES_ROOT", tmp_path)
    (tmp_path / row.storage_path).unlink()
    invoice = SimpleNamespace(invoice_number="TEST", document_file_id=row.id)
    with pytest.raises(HTTPException) as error:
        read_invoice_document_bytes(invoice, case, db)
    assert error.value.status_code == 409
    db.close()


def test_signing_partial_output_failure_can_retry_without_false_completion(
    tmp_path, monkeypatch
):
    from tests.test_canary_sign_service import _session, _user, _case, _request
    from app import canary_sign_service as signing
    from app.models import CanarySignStatus, CaseNote

    db = _session()
    File.__table__.create(db.bind)
    CaseNote.__table__.create(db.bind)
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case)
    monkeypatch.setattr(signing, "FILES_ROOT", tmp_path)
    source = signing._save_case_file(
        db,
        case_id=case.id,
        owner_id=user.id,
        folder_path="",
        filename="Original.pdf",
        mime_type="application/pdf",
        raw=b"original pdf",
    )
    req.source_file_id = source.id
    req.snapshot_pdf_file_id = source.id
    req.sent_by_user_id = user.id
    from tests.test_canary_sign_service import _recipient
    from app.models import CanarySignRecipientStatus
    _recipient(db, req=req, status=CanarySignRecipientStatus.signed)
    db.commit()
    monkeypatch.setattr(signing, "stamp_signed_pdf", lambda *a: b"signed pdf")
    notices = []
    monkeypatch.setattr(
        signing, "_notify_staff_completed", lambda *a: notices.append("completed")
    )
    monkeypatch.setattr(signing, "log_portal_activity", lambda *a, **kw: None)

    def fail(**kw):
        raise OSError("Certificate generation failed")

    monkeypatch.setattr(signing, "build_audit_certificate_pdf", fail)
    with pytest.raises(OSError):
        signing.complete_signing_request(db, req)
    db.rollback()
    assert req.status == CanarySignStatus.pending and req.signed_file_id is None
    assert db.scalar(select(func.count()).select_from(File)) == 1 and notices == []
    assert (tmp_path / source.storage_path).read_bytes() == b"original pdf"
    monkeypatch.setattr(
        signing, "build_audit_certificate_pdf", lambda **kw: b"certificate pdf"
    )
    signing.complete_signing_request(db, req)
    saved = req.signed_file_id
    signing.complete_signing_request(db, req)
    assert req.signed_file_id == saved and notices == ["completed"]
    assert db.scalar(select(func.count()).select_from(File)) == 3
    db.close()


def test_creation_replay_checks_access_and_retained_integrity(tmp_path, monkeypatch):
    db, user, case, payload = compose_fixture(tmp_path, monkeypatch)
    result = creation.compose_office_document(case.id, payload, user, db)
    row = db.get(File, uuid.UUID(result["id"]))
    (tmp_path / row.storage_path).write_bytes(b"corrupt")
    with pytest.raises(HTTPException) as error:
        creation.compose_office_document(case.id, payload, user, db)
    assert error.value.status_code == 409
    from app.models import CaseLockMode, UserRole

    viewer = add_user(db, role=UserRole.user)
    case.lock_mode = CaseLockMode.allow_list
    db.commit()
    with pytest.raises(HTTPException) as error:
        creation.compose_office_document(case.id, payload, viewer, db)
    assert error.value.status_code == 403
    db.close()
