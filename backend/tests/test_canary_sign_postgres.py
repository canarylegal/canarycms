"""Signing transitions against isolated PostgreSQL and real PDF artifacts."""

import uuid
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
import pikepdf
from app.db import SessionLocal
from app import canary_sign_service as sign
from app.models import (
    CanarySignRequest,
    CanarySignRecipient,
    CanarySignField,
    CanarySignFieldType,
    CanarySignStatus,
    CanarySignRecipientStatus,
    CanarySignOrderMode,
    CanarySignAuditEvent,
    CanarySignAuditEventType,
    File,
    User,
)
from app.file_storage import FILES_ROOT
from tests.ledger_test_helpers import add_user, add_case
from app.timeutil import utcnow


@pytest.fixture(autouse=True)
def postgres_only(db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("isolated PostgreSQL required")


def seed(count=1, fillable=False):
    with SessionLocal() as db:
        user = add_user(db)
        case = add_case(db, fee_earner_user_id=user.id)
        writer = pikepdf.Pdf.new()
        writer.add_blank_page(page_size=(612, 792))
        stream = BytesIO()
        writer.save(stream)
        source = sign._save_case_file(
            db,
            case_id=case.id,
            owner_id=user.id,
            folder_path="",
            filename="Synthetic.pdf",
            mime_type="application/pdf",
            raw=stream.getvalue(),
        )
        req = CanarySignRequest(
            id=uuid.uuid4(),
            case_id=case.id,
            source_file_id=source.id,
            snapshot_pdf_file_id=source.id,
            sent_by_user_id=user.id,
            subject="Synthetic review",
            expires_at=utcnow() + timedelta(days=7),
            status=CanarySignStatus.pending,
            order_mode=CanarySignOrderMode.parallel,
            has_fillable_form=fillable,
        )
        db.add(req)
        db.flush()
        recips = []
        fields = []
        for i in range(count):
            r = CanarySignRecipient(
                id=uuid.uuid4(),
                signing_request_id=req.id,
                name=f"Signer {i}",
                email=f"signer{i}@example.com",
                sign_token=uuid.uuid4().hex,
                status=CanarySignRecipientStatus.pending,
                routing_order=i + 1,
            )
            db.add(r)
            db.flush()
            f = CanarySignField(
                id=uuid.uuid4(),
                signing_request_id=req.id,
                recipient_id=r.id,
                field_type=CanarySignFieldType.signature,
                required=True,
                page=1,
                x_pct=10,
                y_pct=10 + i * 15,
                w_pct=30,
                h_pct=10,
                placement_mode="fixed",
            )
            db.add(f)
            recips.append(r.id)
            fields.append(f.id)
        db.commit()
        return req.id, user.id, case.id, recips, fields


def submit(rid, recipient, fid):
    with SessionLocal() as db:
        return sign.submit_signature(
            db,
            db.get(CanarySignRequest, rid),
            db.get(CanarySignRecipient, recipient),
            field_values={str(fid): {"text": "Synthetic signature"}},
        ).status.value


def test_happy_path_real_pdfs_and_certificate():
    rid, _, _, recips, fields = seed()
    assert submit(rid, recips[0], fields[0]) == "completed"
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        for fid in (req.signed_file_id, req.certificate_file_id):
            row = db.get(File, fid)
            raw = (FILES_ROOT / row.storage_path).read_bytes()
            assert len(pikepdf.Pdf.open(BytesIO(raw)).pages) >= 1
            import hashlib

            assert hashlib.sha256(raw).hexdigest() == row.checksum


def test_parallel_final_signers_complete_once(monkeypatch):
    rid, _, _, recips, fields = seed(2)
    barrier = Barrier(2)

    def run(r, f):
        barrier.wait(15)
        return submit(rid, r, f)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, r, f) for r, f in zip(recips, fields)]
        statuses = [f.result(20) for f in futures]
        assert "completed" in statuses
        assert set(statuses) <= {"completed", "pending"}
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        assert req.status == CanarySignStatus.completed and req.signed_file_id
        assert (
            db.scalar(
                select(func.count())
                .select_from(CanarySignAuditEvent)
                .where(
                    CanarySignAuditEvent.signing_request_id == rid,
                    CanarySignAuditEvent.event_type
                    == CanarySignAuditEventType.completed,
                )
            )
            == 1
        )
    assert submit(rid, recips[0], fields[0]) == "completed"


def test_shared_form_has_exactly_one_owner():
    rid, _, _, recips, _ = seed(2, True)
    barrier = Barrier(2)

    def claim(recipient):
        with SessionLocal() as db:
            req = db.get(CanarySignRequest, rid)
            r = db.get(CanarySignRecipient, recipient)
            barrier.wait(15)
            try:
                sign.claim_form_lock(db, req, r)
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        fs = [pool.submit(claim, r) for r in recips]
        assert sorted(f.result(20) for f in fs) == [200, 409]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(CanarySignAuditEvent)
                .where(
                    CanarySignAuditEvent.signing_request_id == rid,
                    CanarySignAuditEvent.event_type
                    == CanarySignAuditEventType.form_locked,
                )
            )
            == 1
        )


def test_stale_submission_cannot_revive_voided_request():
    rid, uid, _, recips, fields = seed()
    with SessionLocal() as stale:
        req = stale.get(CanarySignRequest, rid)
        recipient = stale.get(CanarySignRecipient, recips[0])
        with SessionLocal() as other:
            sign.void_signing_request(
                other,
                req=other.get(CanarySignRequest, rid),
                actor=other.get(User, uid),
                reason="Synthetic cancellation",
            )
        with pytest.raises(HTTPException):
            sign.submit_signature(
                stale,
                req,
                recipient,
                field_values={str(fields[0]): {"text": "Synthetic signature"}},
            )
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        assert req.status == CanarySignStatus.voided and req.signed_file_id is None
        with pytest.raises(HTTPException):
            sign.complete_signing_request(db, req)


def test_signed_download_and_preview_reject_corrupt_bytes():
    rid, _, _, recips, fields = seed()
    submit(rid, recips[0], fields[0])
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        row = db.get(File, req.signed_file_id)
        path = FILES_ROOT / row.storage_path
        original = path.read_bytes()
        try:
            path.write_bytes(b"corrupt synthetic replacement")
            for reader in (sign.read_signed_pdf_bytes, sign.read_portal_preview_pdf):
                with pytest.raises(HTTPException) as exc:
                    reader(db, req)
                assert exc.value.status_code == 409
        finally:
            path.write_bytes(original)


@pytest.mark.parametrize("failure", ["certificate", "queue", "commit"])
def test_failure_rolls_back_signature_and_can_retry(monkeypatch, failure):
    rid, _, _, recips, fields = seed()

    def fail(*a, **k):
        raise RuntimeError("Synthetic failure")

    if failure == "certificate":
        target, name = sign, "build_audit_certificate_pdf"
    elif failure == "queue":
        target, name = sign, "_notify_staff_completed"
    else:
        from sqlalchemy.orm import Session

        target, name = Session, "commit"
    original = getattr(target, name)
    monkeypatch.setattr(target, name, fail)
    with pytest.raises(RuntimeError):
        submit(rid, recips[0], fields[0])
    monkeypatch.setattr(target, name, original)
    with SessionLocal() as db:
        assert db.get(CanarySignRequest, rid).status == CanarySignStatus.pending
        assert (
            db.get(CanarySignRecipient, recips[0]).status
            == CanarySignRecipientStatus.pending
        )
    assert submit(rid, recips[0], fields[0]) == "completed"


def test_sequential_order_then_success():
    rid, _, _, recips, fields = seed(2)
    with SessionLocal() as db:
        db.get(CanarySignRequest, rid).order_mode = CanarySignOrderMode.sequential
        db.commit()
    with pytest.raises(HTTPException):
        submit(rid, recips[1], fields[1])
    assert submit(rid, recips[0], fields[0]) == "pending"
    assert submit(rid, recips[1], fields[1]) == "completed"


@pytest.mark.parametrize("invalid", ["consent", "field", "expired"])
def test_invalid_submission_has_no_signed_artifact(invalid):
    rid, _, _, recips, fields = seed()
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        if invalid == "expired":
            req.expires_at = utcnow() - timedelta(days=1)
            db.commit()
        with pytest.raises(HTTPException):
            sign.submit_signature(
                db,
                req,
                db.get(CanarySignRecipient, recips[0]),
                field_values=(
                    {}
                    if invalid == "field"
                    else {str(fields[0]): {"text": "Synthetic signature"}}
                ),
                consent=invalid != "consent",
            )
    with SessionLocal() as db:
        assert db.get(CanarySignRequest, rid).signed_file_id is None
        assert (
            db.get(CanarySignRecipient, recips[0]).status
            == CanarySignRecipientStatus.pending
        )


def test_unrelated_contact_cannot_access_request():
    from app.portal_browse_service import canary_request_for_contact

    rid, *_ = seed()
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            canary_request_for_contact(db, rid, uuid.uuid4())
        assert exc.value.status_code == 403


def test_missing_snapshot_is_recoverable():
    rid, _, _, recips, fields = seed()
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        row = db.get(File, req.snapshot_pdf_file_id)
        path = FILES_ROOT / row.storage_path
        raw = path.read_bytes()
    path.unlink()
    try:
        with pytest.raises(HTTPException):
            submit(rid, recips[0], fields[0])
    finally:
        path.write_bytes(raw)
    with SessionLocal() as db:
        assert (
            db.get(CanarySignRecipient, recips[0]).status
            == CanarySignRecipientStatus.pending
        )
    assert submit(rid, recips[0], fields[0]) == "completed"


def test_stranded_signed_request_can_retry_completion():
    rid, _, _, recips, fields = seed()
    with SessionLocal() as db:
        db.get(CanarySignRecipient, recips[0]).status = CanarySignRecipientStatus.signed
        db.get(CanarySignField, fields[0]).value = {"text": "Synthetic signature"}
        db.commit()
    assert submit(rid, recips[0], fields[0]) == "completed"


def test_duplicate_concurrent_submission_is_idempotent():
    rid, _, _, recips, fields = seed()
    barrier = Barrier(2)

    def run():
        barrier.wait(15)
        return submit(rid, recips[0], fields[0])

    with ThreadPoolExecutor(max_workers=2) as pool:
        fs = [pool.submit(run) for _ in range(2)]
        assert [f.result(20) for f in fs] == ["completed", "completed"]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(CanarySignAuditEvent)
                .where(
                    CanarySignAuditEvent.signing_request_id == rid,
                    CanarySignAuditEvent.event_type == CanarySignAuditEventType.signed,
                )
            )
            == 1
        )
        with pytest.raises(HTTPException) as exc:
            sign.submit_signature(
                db,
                db.get(CanarySignRequest, rid),
                db.get(CanarySignRecipient, recips[0]),
                field_values={str(fields[0]): {"text": "Changed"}},
            )
        assert exc.value.status_code == 409


def test_corrupt_snapshot_rolls_back_and_retries():
    rid, _, _, recips, fields = seed()
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        path = FILES_ROOT / db.get(File, req.snapshot_pdf_file_id).storage_path
        original = path.read_bytes()
    try:
        path.write_bytes(b"corrupt")
        with pytest.raises(HTTPException) as exc:
            submit(rid, recips[0], fields[0])
        assert exc.value.status_code == 409
    finally:
        path.write_bytes(original)
    assert submit(rid, recips[0], fields[0]) == "completed"


@pytest.mark.parametrize("transition", ["void", "decline"])
def test_terminal_transition_waits_for_inflight_signature(monkeypatch, transition):
    rid, uid, _, recips, fields = seed()
    entered, attempted = Event(), Event()
    original = sign.stamp_signed_pdf

    def stamp(*args, **kwargs):
        entered.set()
        assert attempted.wait(15)
        return original(*args, **kwargs)

    monkeypatch.setattr(sign, "stamp_signed_pdf", stamp)

    def terminal():
        assert entered.wait(15)
        with SessionLocal() as db:
            req = db.get(CanarySignRequest, rid)
            attempted.set()
            with pytest.raises(HTTPException):
                if transition == "void":
                    sign.void_signing_request(
                        db, req=req, actor=db.get(User, uid), reason="race"
                    )
                else:
                    sign.decline_signing(
                        db, req, db.get(CanarySignRecipient, recips[0]), reason="race"
                    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        signing = pool.submit(submit, rid, recips[0], fields[0])
        ending = pool.submit(terminal)
        assert signing.result(20) == "completed"
        ending.result(20)
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        assert req.status == CanarySignStatus.completed and req.voided_at is None


def test_completion_rejects_pending_recipients():
    rid, *_ = seed()
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        with pytest.raises(HTTPException) as exc:
            sign.complete_signing_request(db, req)
        assert exc.value.status_code == 409 and req.signed_file_id is None


def test_stale_view_cannot_overwrite_signed_recipient():
    rid,_,_,recips,fields=seed()
    with SessionLocal() as stale:
        req=stale.get(CanarySignRequest,rid);recipient=stale.get(CanarySignRecipient,recips[0])
        assert submit(rid,recips[0],fields[0])=='completed'
        sign.record_view(stale,req,recipient)
    with SessionLocal() as db:
        assert db.get(CanarySignRecipient,recips[0]).status==CanarySignRecipientStatus.signed


def test_retry_ignores_non_persisted_placement_metadata():
    rid,_,_,recips,fields=seed();assert submit(rid,recips[0],fields[0])=='completed'
    with SessionLocal() as db:
        result=sign.submit_signature(db,db.get(CanarySignRequest,rid),db.get(CanarySignRecipient,recips[0]),field_values={str(fields[0]):{'text':'Synthetic signature','page':1}})
        assert result.status==CanarySignStatus.completed


@pytest.mark.parametrize("artifact", ["snapshot_pdf_file_id", "signed_file_id", "certificate_file_id"])
def test_legacy_missing_checksum_preserves_access_without_inventing_baseline(caplog, artifact):
    rid, _, _, recips, fields = seed()
    assert submit(rid, recips[0], fields[0]) == "completed"
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        row = db.get(File, getattr(req, artifact))
        row.checksum = None
        db.commit()
        readers = {
            "snapshot_pdf_file_id": sign.read_snapshot_pdf_bytes,
            "signed_file_id": sign.read_signed_pdf_bytes,
            "certificate_file_id": sign.read_certificate_pdf_bytes,
        }
        result = readers[artifact](db, req)
        raw = result if isinstance(result, bytes) else result[0]
        assert raw == (FILES_ROOT / row.storage_path).read_bytes()
        assert row.checksum is None
        assert "no integrity baseline" in caplog.text
