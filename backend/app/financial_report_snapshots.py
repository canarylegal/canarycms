"""Immutable approval artifacts with a hash-linked version history and fail-closed reads."""

import hashlib
import json
import os
import uuid
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from fastapi import HTTPException
from sqlalchemy import select
from app.accounting_periods import lock_periods
from app.audit import log_event
from app.bank_integrity import require_banking
from app.deps import require_case_access
from app.financial_snapshot_capture import (
    canonical,
    capture_data,
    firm_report_arguments,
    render_firm_docx,
    render_bank_html,
    encode,
)
from app.models import AuditEvent, FinancialReportSnapshot
from app.timeutil import utcnow

MAX_BYTES = 64 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def latest_snapshot(db, kind, source_id):
    return db.scalar(
        select(FinancialReportSnapshot)
        .where(
            FinancialReportSnapshot.source_kind == kind,
            FinancialReportSnapshot.source_id == source_id,
        )
        .order_by(FinancialReportSnapshot.version.desc())
        .limit(1)
    )


def _reopening(db, kind, source_id):
    action = "reconciliation.reopen" if kind == "firm" else "bank.reconciliation.reopen"
    return db.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == action, AuditEvent.entity_id == str(source_id))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )


def archive_approval(db, kind, row, actor):
    # Bank approval also excludes firm-wide writes while capturing its source evidence.
    lock_periods(db, exclusive=True)
    if (
        str(getattr(row.status, "value", row.status)) != "approved"
        or not row.approved_at
    ):
        raise HTTPException(409, "Only an approved reconciliation can be archived")
    previous = latest_snapshot(db, kind, row.id)
    event = _reopening(db, kind, row.id)
    if previous:
        manifest = verify_chain(db, previous)
        if not event or manifest.get("reopening_audit_id") == str(event.id):
            raise HTTPException(
                409,
                "A new audited reopening is required before another archive version",
            )
    data = capture_data(db, kind, row)
    source = data["reconciliation"][0]
    if kind == "firm":
        arguments = firm_report_arguments(data)
        data["report_arguments"] = arguments
        artifact_name = "report.docx"
        artifact = render_firm_docx(arguments)
    else:
        artifact_name = "report.html"
        artifact = render_bank_html(data)
    files = {"data.json": canonical(data), artifact_name: artifact}
    if sum(map(len, files.values())) > MAX_BYTES:
        raise HTTPException(
            413, "Approval archive exceeds the supported size; review before approving"
        )
    identity = uuid.uuid4()
    created = utcnow()
    version = previous.version + 1 if previous else 1
    manifest = dict(
        schema_version=1,
        snapshot_id=str(identity),
        source_kind=kind,
        source_id=str(row.id),
        version=version,
        previous_id=str(previous.id) if previous else None,
        previous_archive_sha256=previous.archive_sha256 if previous else None,
        approved_by_user_id=str(actor.id),
        approved_at=source["approved_at"],
        created_at=encode(created),
        build_commit=os.getenv("CANARY_BUILD_COMMIT")
        or os.getenv("BUILD_COMMIT")
        or "unknown",
        renderer_version=1,
        period_end_date=source["period_end_date"],
        filters=dict(
            scope="firm" if kind == "firm" else "bank",
            bank_id=source.get("firm_bank_account_id"),
            approved_only=True,
            cutoff="inclusive UTC day",
        ),
        case_ids=sorted({e["case_id"] for e in data["ledger"]}),
        reopening_audit_id=str(event.id) if event else None,
        revision_reason=(
            json.loads(event.meta_json or "{}").get("reason") if event else None
        ),
        files={
            name: dict(sha256=digest(content), bytes=len(content))
            for name, content in files.items()
        },
    )
    manifest_bytes = canonical(manifest)
    out = BytesIO()
    with ZipFile(out, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        for name, content in files.items():
            archive.writestr(name, content)
    content = out.getvalue()
    saved = FinancialReportSnapshot(
        id=identity,
        source_kind=kind,
        source_id=row.id,
        version=version,
        previous_id=previous.id if previous else None,
        approved_by_user_id=actor.id,
        approved_at=row.approved_at,
        created_at=created,
        manifest_json=manifest_bytes.decode(),
        manifest_sha256=digest(manifest_bytes),
        archive_sha256=digest(content),
        archive_bytes=content,
    )
    db.add(saved)
    db.flush()
    log_event(
        db,
        actor_user_id=actor.id,
        action="financial.snapshot.approve",
        entity_type="financial_report_snapshot",
        entity_id=str(saved.id),
        meta=dict(
            source_kind=kind,
            source_id=str(row.id),
            version=version,
            archive_sha256=saved.archive_sha256,
            previous_id=manifest["previous_id"],
        ),
    )
    return saved


def verify_snapshot(snapshot):
    try:
        raw = snapshot.manifest_json.encode()
        content = bytes(snapshot.archive_bytes)
        if (
            digest(raw) != snapshot.manifest_sha256
            or digest(content) != snapshot.archive_sha256
        ):
            raise ValueError("hash")
        manifest = json.loads(raw)
        artifact = "report.docx" if snapshot.source_kind == "firm" else "report.html"
        if manifest["schema_version"] != 1 or manifest["renderer_version"] != 1:
            raise ValueError("unsupported schema")
        if set(manifest["files"]) != {"data.json", artifact}:
            raise ValueError("required artifacts")
        if (
            manifest["snapshot_id"],
            manifest["source_kind"],
            manifest["source_id"],
            manifest["version"],
            manifest["previous_id"],
        ) != (
            str(snapshot.id),
            snapshot.source_kind,
            str(snapshot.source_id),
            snapshot.version,
            str(snapshot.previous_id) if snapshot.previous_id else None,
        ):
            raise ValueError("identity")
        if manifest["approved_by_user_id"] != str(snapshot.approved_by_user_id):
            raise ValueError("approver")
        # Compare parsed instants, since PostgreSQL normalizes timezone representation.
        from datetime import datetime, timezone

        actual = snapshot.approved_at
        actual = (
            actual.replace(tzinfo=timezone.utc) if actual.tzinfo is None else actual
        )
        expected = datetime.fromisoformat(manifest["approved_at"])
        expected = (
            expected.replace(tzinfo=timezone.utc)
            if expected.tzinfo is None
            else expected
        )
        if actual != expected:
            raise ValueError("approval time")
        created = snapshot.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created != datetime.fromisoformat(manifest["created_at"]):
            raise ValueError("creation time")
        with ZipFile(BytesIO(content)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != set(manifest["files"]) | {
                "manifest.json"
            }:
                raise ValueError("members")
            if sum(i.file_size for i in archive.infolist()) > MAX_BYTES + len(raw):
                raise ValueError("size")
            if archive.read("manifest.json") != raw:
                raise ValueError("manifest")
            for name, entry in manifest["files"].items():
                data = archive.read(name)
                if len(data) != entry["bytes"] or digest(data) != entry["sha256"]:
                    raise ValueError("artifact")
        return manifest
    except Exception as exc:
        raise HTTPException(
            409,
            "Archived financial report failed integrity verification; no report was released",
        ) from exc


def verify_chain(db, snapshot):
    current = snapshot
    seen = set()
    result = None
    while current:
        if current.id in seen:
            raise HTTPException(409, "Invalid financial archive version chain")
        seen.add(current.id)
        manifest = verify_snapshot(current)
        if result is None:
            result = manifest
        if current.previous_id is None:
            if current.version != 1 or manifest["previous_archive_sha256"] is not None:
                raise HTTPException(409, "Invalid archive root")
            break
        previous = db.get(FinancialReportSnapshot, current.previous_id)
        if (
            previous is None
            or previous.source_kind != current.source_kind
            or previous.source_id != current.source_id
            or previous.version != current.version - 1
            or manifest["previous_archive_sha256"] != previous.archive_sha256
        ):
            raise HTTPException(409, "Invalid financial archive version chain")
        current = previous
    return result


def authorized_artifact(db, snapshot, actor, *, summary_only=False):
    require_banking(actor, db)
    manifest = verify_chain(db, snapshot)
    if not summary_only:
        for case_id in manifest["case_ids"]:
            require_case_access(uuid.UUID(case_id), actor, db)
    return manifest


def download_snapshot(db, snapshot, actor, *, summary_only=False):
    try:
        manifest = authorized_artifact(db, snapshot, actor, summary_only=summary_only)
    except HTTPException as exc:
        if exc.status_code == 409:
            identity, actor_id = str(snapshot.id), actor.id
            db.rollback()
            log_event(
                db,
                actor_user_id=actor_id,
                action="financial.snapshot.integrity_failure",
                entity_type="financial_report_snapshot",
                entity_id=identity,
                meta={"operation": "download", "released": False},
            )
            db.commit()
        raise
    if summary_only:
        if snapshot.source_kind != "firm":
            raise HTTPException(404, "Summary not available")
        with ZipFile(BytesIO(snapshot.archive_bytes)) as archive:
            content = archive.read("report.docx")
        name = (
            f'Client account reconcile report — {manifest["period_end_date"][:7]}.docx'
        )
        media = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    else:
        content = bytes(snapshot.archive_bytes)
        name = f"approved-{snapshot.source_kind}-{snapshot.source_id}-v{snapshot.version}.zip"
        media = "application/zip"
    log_event(
        db,
        actor_user_id=actor.id,
        action="financial.snapshot.download",
        entity_type="financial_report_snapshot",
        entity_id=str(snapshot.id),
        meta=dict(
            version=snapshot.version,
            artifact="report.docx" if summary_only else "archive.zip",
            sha256=digest(content),
        ),
    )
    db.commit()  # Do not release bytes unless access auditing committed successfully.
    return content, name, media
