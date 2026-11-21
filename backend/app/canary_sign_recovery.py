"""Operator-only diagnostics and reviewed recovery; never invoked by scheduled jobs."""

from __future__ import annotations
import hashlib
import io
import json
import uuid
from pathlib import Path
import pikepdf
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models import (
    CanarySignRequest,
    CanarySignRecipient,
    CanarySignAuditEvent,
    CanarySignRecovery,
    File,
    User,
    UserRole,
)
from app.file_storage import FILES_ROOT
from app.document_durability import safe_path
from app.audit import log_event
from app.timeutil import utcnow
from app import canary_sign_service as signing

ARTIFACTS = {
    "snapshot": "snapshot_pdf_file_id",
    "signed": "signed_file_id",
    "certificate": "certificate_file_id",
}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_state(db, file_id):
    row = db.get(File, file_id) if file_id else None
    if row is None:
        return {"id": str(file_id) if file_id else None, "state": "missing_reference"}
    result = {
        "id": str(row.id),
        "case_id": str(row.case_id),
        "storage_path": row.storage_path,
        "stored_sha256": row.checksum,
        "size_bytes": row.size_bytes,
    }
    try:
        path = safe_path(FILES_ROOT, row.storage_path)
        with path.open("rb") as stream:
            result["observed_sha256"] = hashlib.file_digest(
                stream, "sha256"
            ).hexdigest()
        result["observed_size"] = path.stat().st_size
        result["state"] = (
            "legacy_without_baseline"
            if not row.checksum
            else (
                "verified"
                if row.checksum == result["observed_sha256"]
                else "checksum_mismatch"
            )
        )
    except HTTPException:
        result["state"] = "invalid_storage_path"
    except FileNotFoundError:
        result["state"] = "missing_file"
    except (ValueError, OSError):
        result["state"] = "unreadable_file"
    return result


def request_state(db, req, artifact):
    return {
        "request_id": str(req.id),
        "case_id": str(req.case_id),
        "status": req.status.value,
        "updated_at": req.updated_at.isoformat(),
        "completed_at": str(req.completed_at),
        "voided_at": str(req.voided_at),
        "artifact": artifact,
        "references": {
            key: str(getattr(req, attr)) if getattr(req, attr) else None
            for key, attr in ARTIFACTS.items()
        },
        "file": file_state(db, getattr(req, ARTIFACTS[artifact])),
    }


def diagnose(db):
    """No state transitions, expiry marking, files written or commits."""
    findings = []
    count = 0
    for req in db.scalars(select(CanarySignRequest).order_by(CanarySignRequest.id)):
        count += 1
        states = list(
            db.scalars(
                select(CanarySignRecipient.status).where(
                    CanarySignRecipient.signing_request_id == req.id
                )
            )
        )
        signed = bool(states) and all(s.value == "signed" for s in states)
        codes = []
        if req.status.value == "pending" and signed:
            codes.append("all_signed_pending")
        if req.status.value == "completed":
            if not signed:
                codes.append("completed_without_all_signers")
            if not req.completed_at:
                codes.append("missing_completed_timestamp")
            if req.voided_at:
                codes.append("completed_and_voided")
            if not db.scalar(
                select(CanarySignAuditEvent.id)
                .where(
                    CanarySignAuditEvent.signing_request_id == req.id,
                    CanarySignAuditEvent.event_type == "completed",
                )
                .limit(1)
            ):
                codes.append("missing_completion_audit")
        if req.status.value in ("voided", "declined", "expired") and (
            req.signed_file_id or req.certificate_file_id
        ):
            codes.append("terminal_state_with_artifacts")
        artifacts = {}
        for kind, attr in ARTIFACTS.items():
            if (
                kind != "snapshot"
                and req.status.value != "completed"
                and not getattr(req, attr)
            ):
                continue
            state = file_state(db, getattr(req, attr))
            artifacts[kind] = state
            if state.get("case_id") and state["case_id"] != str(req.case_id):
                codes.append(kind + ":cross_matter_reference")
            if state["state"] != "verified":
                codes.append(kind + ":" + state["state"])
            if (
                "observed_size" in state
                and state["observed_size"] != state["size_bytes"]
            ):
                codes.append(kind + ":size_mismatch")
        if codes:
            findings.append(
                {"request_id": str(req.id), "codes": codes, "artifacts": artifacts}
            )
    return {"requests_checked": count, "findings": findings, "corrections_applied": 0}


def evidence(db, request_id, artifact, source_label):
    """Export provenance from an independently restored, verified backup database/files pair."""
    if artifact not in ARTIFACTS or not source_label.strip():
        raise ValueError("Artifact and backup source label required")
    req = db.get(CanarySignRequest, request_id)
    if req is None or req.status.value != "completed":
        raise ValueError("Completed backup request required")
    state = file_state(db, getattr(req, ARTIFACTS[artifact]))
    if state["state"] not in ("verified", "legacy_without_baseline") or state[
        "case_id"
    ] != str(req.case_id):
        raise ValueError("Backup artifact missing, corrupt or outside the matter")
    row = db.get(File, uuid.UUID(state["id"]))
    raw = safe_path(FILES_ROOT, row.storage_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != state["observed_sha256"]:
        raise ValueError("Backup changed during export")
    with pikepdf.Pdf.open(io.BytesIO(raw)) as pdf:
        if not len(pdf.pages):
            raise ValueError("Empty PDF")
    return {
        "version": 1,
        "request_id": str(req.id),
        "case_id": str(req.case_id),
        "artifact": artifact,
        "file_id": str(row.id),
        "filename": row.original_filename,
        "sha256": state["observed_sha256"],
        "source_label": source_label,
        "source_checksum": row.checksum,
        "observed_at": utcnow().isoformat(),
    }, raw


def administrator(db, actor_id):
    user = db.get(User, actor_id)
    if not user or not user.is_active or user.role != UserRole.admin:
        raise ValueError("Active administrator required")
    return user


def validate_evidence(req, artifact, proof, raw):
    if (
        proof.get("version") != 1
        or proof.get("request_id") != str(req.id)
        or proof.get("case_id") != str(req.case_id)
        or proof.get("artifact") != artifact
    ):
        raise ValueError("Evidence belongs to another request, matter or artifact")
    if (
        not proof.get("source_label")
        or not proof.get("observed_at")
        or hashlib.sha256(raw).hexdigest() != proof.get("sha256")
    ):
        raise ValueError("Evidence changed or lacks provenance")
    with pikepdf.Pdf.open(io.BytesIO(raw)) as pdf:
        if not len(pdf.pages):
            raise ValueError("Empty PDF")


def prepare(
    db, *, request_id, artifact, action, actor_id, reason, proof, raw, operation_id
):
    administrator(db, actor_id)
    if artifact not in ARTIFACTS or action not in ("baseline", "restore"):
        raise ValueError("Unknown recovery action")
    if not reason.strip() or len(reason) > 2000:
        raise ValueError("Review reason required (up to 2000 characters)")
    req = db.get(CanarySignRequest, request_id)
    if not req or req.status.value != "completed" or req.voided_at:
        raise ValueError("Unambiguous completed request required")
    validate_evidence(req, artifact, proof, raw)
    before = request_state(db, req, artifact)
    f = before["file"]
    if f.get("case_id") and f["case_id"] != str(req.case_id):
        raise ValueError("Cross-matter reference requires separate investigation")
    if action == "baseline":
        if (
            f["state"] != "legacy_without_baseline"
            or f["observed_sha256"] != proof["sha256"]
            or f["id"] != proof["file_id"]
        ):
            raise ValueError(
                "Baseline requires unchanged legacy bytes and the same backup file identity"
            )
    elif artifact == "snapshot" or f["state"] not in (
        "missing_reference",
        "missing_file",
        "checksum_mismatch",
    ):
        raise ValueError(
            "Restore only missing or mismatching signed artifacts; never replace a healthy file"
        )
    plan = {
        "version": 1,
        "operation_id": str(operation_id),
        "actor_id": str(actor_id),
        "action": action,
        "reason": reason.strip(),
        "before": before,
        "evidence": proof,
    }
    plan["plan_sha256"] = digest(plan)
    return plan


def apply(db, plan, raw, *, approved_sha256):
    """Caller commits once; changes, audit and immutable receipt share the transaction."""
    content = {key: value for key, value in plan.items() if key != "plan_sha256"}
    fingerprint = digest(content)
    if fingerprint != plan.get("plan_sha256") or fingerprint != approved_sha256:
        raise ValueError("Exact reviewed plan hash required")
    if db.get_bind().dialect.name != "postgresql":
        raise ValueError("PostgreSQL required")
    actor = administrator(db, uuid.UUID(plan["actor_id"]))
    operation_id = uuid.UUID(plan["operation_id"])
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": operation_id.int & ((1 << 63) - 1)},
    )
    existing = db.get(CanarySignRecovery, operation_id)
    if existing:
        if existing.plan_sha256 != fingerprint:
            raise ValueError("Operation ID already used for another plan")
        return existing.record
    req = db.execute(
        select(CanarySignRequest)
        .where(CanarySignRequest.id == uuid.UUID(plan["before"]["request_id"]))
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    artifact = plan["before"]["artifact"]
    fid = getattr(req, ARTIFACTS[artifact])
    if fid:
        db.execute(
            select(File)
            .where(File.id == fid)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
    fresh = prepare(
        db,
        request_id=req.id,
        artifact=artifact,
        action=plan["action"],
        actor_id=actor.id,
        reason=plan["reason"],
        proof=plan["evidence"],
        raw=raw,
        operation_id=operation_id,
    )
    if fresh != plan:
        raise ValueError("State changed since review; prepare a new plan")
    if plan["action"] == "baseline":
        db.get(File, fid).checksum = plan["evidence"]["sha256"]
    else:
        source = db.get(File, req.source_file_id)
        restored = signing._save_case_file(
            db,
            case_id=req.case_id,
            owner_id=actor.id,
            folder_path=source.folder_path if source else "",
            filename=Path(plan["evidence"]["filename"]).name,
            mime_type="application/pdf",
            raw=raw,
            parent_file_id=req.source_file_id,
        )
        setattr(req, ARTIFACTS[artifact], restored.id)
    db.flush()
    after = request_state(db, req, artifact)
    if (
        after["file"]["state"] != "verified"
        or after["file"]["observed_sha256"] != plan["evidence"]["sha256"]
    ):
        raise ValueError("Artifact changed during recovery; no success recorded")
    record = {"plan": plan, "after": after, "applied_at": utcnow().isoformat()}
    db.add(
        CanarySignRecovery(
            id=operation_id,
            request_id=req.id,
            actor_id=actor.id,
            plan_sha256=fingerprint,
            record=record,
        )
    )
    log_event(
        db,
        actor_user_id=actor.id,
        action="canary_sign.recovery.applied",
        entity_type="canary_sign_request",
        entity_id=str(req.id),
        meta={
            "operation_id": str(operation_id),
            "plan_sha256": fingerprint,
            "action": plan["action"],
            "artifact": artifact,
            "reason": plan["reason"],
        },
    )
    db.flush()
    return record


def receipts(db):
    """Stable read-only manifest for comparing recovery evidence across restore/restart."""
    result = []
    for row in db.scalars(select(CanarySignRecovery).order_by(CanarySignRecovery.id)):
        plan = row.record["plan"]
        if (
            digest({k: v for k, v in plan.items() if k != "plan_sha256"})
            != row.plan_sha256
            or plan["plan_sha256"] != row.plan_sha256
            or plan["operation_id"] != str(row.id)
            or plan["actor_id"] != str(row.actor_id)
            or plan["before"]["request_id"] != str(row.request_id)
            or row.record["after"]["file"]["observed_sha256"]
            != plan["evidence"]["sha256"]
        ):
            raise ValueError("Recovery receipt integrity check failed")
        result.append(
            {
                "id": str(row.id),
                "record_sha256": digest(row.record),
                "plan_sha256": row.plan_sha256,
            }
        )
    return {"receipts": result}
