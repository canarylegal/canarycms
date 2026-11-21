import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from app.db import SessionLocal, begin_report_snapshot
from app import canary_sign_recovery as recovery
from app.models import CanarySignRequest, CanarySignRecovery, File, User, UserRole
from tests.test_canary_sign_postgres import seed, submit


@pytest.fixture(autouse=True)
def postgres_only(db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("isolated PostgreSQL required")


def fixture(action="baseline"):
    rid, uid, _, recipients, fields = seed()
    submit(rid, recipients[0], fields[0])
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        proof, raw = recovery.evidence(
            db, rid, "certificate", "Synthetic independently verified backup"
        )
        fid = req.certificate_file_id
        if action == "baseline":
            db.get(File, fid).checksum = None
        else:
            req.certificate_file_id = None
        db.commit()
        plan = recovery.prepare(
            db,
            request_id=rid,
            artifact="certificate",
            action=action,
            actor_id=uid,
            reason="Synthetic reviewed recovery",
            proof=proof,
            raw=raw,
            operation_id=uuid.uuid4(),
        )
    return rid, uid, fid, plan, raw


def run(plan, raw):
    with SessionLocal() as db:
        result = recovery.apply(db, plan, raw, approved_sha256=plan["plan_sha256"])
        db.commit()
        return result


def test_diagnostics_and_plan_do_not_correct_data():
    rid, _, fid, plan, raw = fixture()
    with SessionLocal() as db:
        begin_report_snapshot(db)
        report = recovery.diagnose(db)
        assert any(
            f["request_id"] == str(rid)
            and "certificate:legacy_without_baseline" in f["codes"]
            for f in report["findings"]
        )
        assert db.get(File, fid).checksum is None
        assert db.get(CanarySignRecovery, uuid.UUID(plan["operation_id"])) is None
        assert report["corrections_applied"] == 0


def test_baseline_audited_and_replay_safe():
    rid, _, fid, plan, raw = fixture()
    result = run(plan, raw)
    assert run(plan, raw) == result
    with SessionLocal() as db:
        assert db.get(File, fid).checksum == plan["evidence"]["sha256"]
        assert db.get(CanarySignRequest, rid).certificate_file_id == fid
        assert (
            db.scalar(
                select(func.count())
                .select_from(CanarySignRecovery)
                .where(CanarySignRecovery.id == uuid.UUID(plan["operation_id"]))
            )
            == 1
        )
        assert (
            db.execute(
                text(
                    "SELECT count(*) FROM audit_event WHERE action='canary_sign.recovery.applied' AND entity_id=:rid"
                ),
                {"rid": str(rid)},
            ).scalar_one()
            == 1
        )


def test_restore_retains_original_and_does_not_fabricate_completion():
    rid, _, fid, plan, raw = fixture("restore")
    result = run(plan, raw)
    assert run(plan, raw) == result
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        assert req.certificate_file_id != fid
        assert db.get(File, fid) is not None
        assert str(req.completed_at) == plan["before"]["completed_at"]
        assert (
            recovery.file_state(db, req.certificate_file_id)["observed_sha256"]
            == plan["evidence"]["sha256"]
        )


@pytest.mark.parametrize("action", ["baseline", "restore"])
def test_concurrent_replay_creates_one_receipt(action):
    _, _, _, plan, raw = fixture(action)
    barrier = Barrier(2)

    def attempt():
        barrier.wait(10)
        return run(plan, raw)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt) for _ in range(2)]
        assert futures[0].result(20) == futures[1].result(20)


@pytest.mark.parametrize("action", ["baseline", "restore"])
def test_audit_failure_rolls_back_and_retries(monkeypatch, action):
    rid, _, fid, plan, raw = fixture(action)

    def fail(*a, **k):
        raise RuntimeError("Injected audit failure")

    original = recovery.log_event
    monkeypatch.setattr(recovery, "log_event", fail)
    with pytest.raises(RuntimeError):
        run(plan, raw)
    with SessionLocal() as db:
        assert db.get(CanarySignRecovery, uuid.UUID(plan["operation_id"])) is None
        if action == "baseline":
            assert db.get(File, fid).checksum is None
        else:
            assert db.get(CanarySignRequest, rid).certificate_file_id is None
    monkeypatch.setattr(recovery, "log_event", original)
    run(plan, raw)


def test_changes_after_review_and_evidence_tampering_rejected():
    _, _, fid, plan, raw = fixture()
    with pytest.raises(ValueError):
        run(plan, raw + b"altered")
    altered = {**plan, "reason": "unreviewed change"}
    with pytest.raises(ValueError):
        run(altered, raw)
    with SessionLocal() as db:
        row = db.get(File, fid)
        path = recovery.safe_path(recovery.FILES_ROOT, row.storage_path)
        original = path.read_bytes()
        path.write_bytes(original + b"altered")
    try:
        with pytest.raises(ValueError):
            run(plan, raw)
    finally:
        path.write_bytes(original)
    run(plan, raw)


def test_cross_request_evidence_and_non_admin_denied():
    rid, uid, _, plan, raw = fixture()
    with SessionLocal() as db:
        proof = {**plan["evidence"], "request_id": str(uuid.uuid4())}
        with pytest.raises(ValueError):
            recovery.prepare(
                db,
                request_id=rid,
                artifact="certificate",
                action="baseline",
                actor_id=uid,
                reason="reviewed",
                proof=proof,
                raw=raw,
                operation_id=uuid.uuid4(),
            )
        db.get(User, uid).is_active = False
        db.commit()
    with pytest.raises(ValueError):
        run(plan, raw)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE canary_sign_recovery SET plan_sha256='changed' WHERE id=:id",
        "DELETE FROM canary_sign_recovery WHERE id=:id",
        "TRUNCATE canary_sign_recovery",
    ],
)
def test_receipts_cannot_be_rewritten(sql):
    _, _, _, plan, raw = fixture()
    run(plan, raw)
    with SessionLocal() as db:
        with pytest.raises(DBAPIError):
            db.execute(text(sql), {"id": uuid.UUID(plan["operation_id"])})


def test_different_operations_cannot_apply_stale_plan_twice():
    rid, uid, _, first, raw = fixture()
    with SessionLocal() as db:
        second = recovery.prepare(
            db,
            request_id=rid,
            artifact="certificate",
            action="baseline",
            actor_id=uid,
            reason="second review",
            proof=first["evidence"],
            raw=raw,
            operation_id=uuid.uuid4(),
        )
    run(first, raw)
    with pytest.raises(ValueError):
        run(second, raw)


def test_operation_id_cannot_be_reused_for_different_plan():
    _, _, _, first, raw = fixture()
    run(first, raw)
    second = {**first, "reason": "different plan"}
    second["plan_sha256"] = recovery.digest(
        {k: v for k, v in second.items() if k != "plan_sha256"}
    )
    with pytest.raises(ValueError):
        run(second, raw)


def test_committed_but_lost_response_replays_receipt(monkeypatch):
    from sqlalchemy.orm import Session

    _, _, _, plan, raw = fixture("restore")
    original = Session.commit

    def lost(self):
        original(self)
        raise RuntimeError("Response lost after commit")

    monkeypatch.setattr(Session, "commit", lost)
    with pytest.raises(RuntimeError):
        run(plan, raw)
    monkeypatch.setattr(Session, "commit", original)
    result = run(plan, raw)
    assert result["after"]["file"]["state"] == "verified"


def test_invalid_storage_path_is_diagnosed_without_reading_outside_root():
    rid, _, fid, _, _ = fixture()
    with SessionLocal() as db:
        db.get(File, fid).storage_path = "../../outside.pdf"
        db.commit()
        state = recovery.file_state(db, fid)
        assert state["state"] == "invalid_storage_path"
        assert "observed_sha256" not in state


def test_restore_write_failure_does_not_publish_reference(monkeypatch):
    rid, _, _, plan, raw = fixture("restore")

    def fail(*args, **kwargs):
        raise OSError("Disk failure")

    original = recovery.signing._save_case_file
    monkeypatch.setattr(recovery.signing, "_save_case_file", fail)
    with pytest.raises(OSError):
        run(plan, raw)
    with SessionLocal() as db:
        assert db.get(CanarySignRequest, rid).certificate_file_id is None
        assert db.get(CanarySignRecovery, uuid.UUID(plan["operation_id"])) is None
    monkeypatch.setattr(recovery.signing, "_save_case_file", original)
    run(plan, raw)


def test_concurrent_different_plans_only_one_applies():
    rid, uid, _, first, raw = fixture()
    with SessionLocal() as db:
        second = recovery.prepare(
            db,
            request_id=rid,
            artifact="certificate",
            action="baseline",
            actor_id=uid,
            reason="other review",
            proof=first["evidence"],
            raw=raw,
            operation_id=uuid.uuid4(),
        )
    barrier = Barrier(2)

    def attempt(plan):
        barrier.wait(10)
        try:
            run(plan, raw)
            return "applied"
        except ValueError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        fs = [pool.submit(attempt, p) for p in (first, second)]
        assert sorted(f.result(20) for f in fs) == ["applied", "stale"]


@pytest.mark.parametrize("action", ["baseline", "restore"])
@pytest.mark.parametrize("stage", ["prepare", "apply"])
@pytest.mark.parametrize("damage", ["timestamp", "unsigned_recipient", "signed_timestamp", "completion_audit"])
def test_recovery_rejects_contradictory_completion(action, stage, damage):
    from sqlalchemy import delete
    from app.models import CanarySignRecipient, CanarySignAuditEvent

    rid, uid, fid, plan, raw = fixture(action)
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        if damage == "timestamp":
            req.completed_at = None
        elif damage in ("unsigned_recipient", "signed_timestamp"):
            recipient = db.scalar(select(CanarySignRecipient).where(CanarySignRecipient.signing_request_id == rid))
            if damage == "unsigned_recipient":
                recipient.status = "pending"
            recipient.signed_at = None
        else:
            db.execute(delete(CanarySignAuditEvent).where(
                CanarySignAuditEvent.signing_request_id == rid,
                CanarySignAuditEvent.event_type == "completed",
            ))
        db.commit()
        with pytest.raises(ValueError):
            if stage == "prepare":
                recovery.prepare(db, request_id=rid, artifact="certificate", action=action,
                    actor_id=uid, reason="Synthetic reviewed evidence", proof=plan["evidence"],
                    raw=raw, operation_id=uuid.uuid4())
            else:
                recovery.apply(db, plan, raw, approved_sha256=plan["plan_sha256"])
        db.rollback()
        assert db.get(CanarySignRecovery, uuid.UUID(plan["operation_id"])) is None
        assert db.get(CanarySignRequest, rid).certificate_file_id == (fid if action == "baseline" else None)
        if action == "baseline":
            assert db.get(File, fid).checksum is None


@pytest.mark.parametrize("changed", ["recipient_timestamp", "audit_detail"])
def test_recovery_rejects_changed_but_still_complete_evidence(changed):
    from datetime import timedelta
    from app.models import CanarySignRecipient, CanarySignAuditEvent

    rid, _, _, plan, raw = fixture("restore")
    with SessionLocal() as db:
        if changed == "recipient_timestamp":
            row = db.scalar(select(CanarySignRecipient).where(CanarySignRecipient.signing_request_id == rid))
            row.signed_at += timedelta(seconds=1)
        else:
            row = db.scalar(select(CanarySignAuditEvent).where(
                CanarySignAuditEvent.signing_request_id == rid,
                CanarySignAuditEvent.event_type == "completed",
            ))
            row.detail = {**(row.detail or {}), "changed": True}
        db.commit()
    with pytest.raises(ValueError, match="State changed since review"):
        run(plan, raw)
    with SessionLocal() as db:
        assert db.get(CanarySignRequest, rid).certificate_file_id is None
        assert db.get(CanarySignRecovery, uuid.UUID(plan["operation_id"])) is None
