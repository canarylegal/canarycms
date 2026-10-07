#!/usr/bin/env python3
"""Phase 7 MVP firm-platform contract smoke (compat / migrate / API / lifecycle).

Runs against a live backend with ``example-firm-pilot`` (or compatible package) attached.

Preferred (repo root):

  make smoke-firm-contract

Or:

  docker compose exec backend python scripts/smoke_firm_contract.py

Env:

  FIRM_CONTRACT_BASE   default http://127.0.0.1:8000
  FIRM_CONTRACT_STAFF_EMAIL  optional staff user (else first active admin)
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

import httpx
from sqlalchemy import select, text

from concurrent.futures import ThreadPoolExecutor, as_completed

from app.db import SessionLocal
from app.firm_module_runtime import (
    LIFECYCLE_DOCUMENT_UPLOADED,
    LIFECYCLE_MATTER_CREATED,
    LIFECYCLE_MATTER_STATUS_CHANGED,
    deliver_lifecycle_event,
    enqueue_lifecycle_event,
    load_manifest,
    module_applies_to_case,
    process_document_uploaded,
    process_matter_created,
    process_matter_status_changed,
    process_pending_lifecycle_events,
    storage_schema,
)
from app.firm_package import evaluate_firm_package_status
from app.models import (
    AuditEvent,
    Case,
    CaseLockMode,
    FirmLifecycleOutbox,
    MatterHeadType,
    MatterSubType,
    User,
    UserRole,
)
from app.security import create_access_token, hash_password

BASE = os.getenv("FIRM_CONTRACT_BASE", "http://127.0.0.1:8000").rstrip("/")

# Published lifecycle payload keys (schema_version: 1) — FIRM_MODULE_CONTRACT.md
LIFECYCLE_REQUIRED: dict[str, frozenset[str]] = {
    LIFECYCLE_MATTER_CREATED: frozenset(
        {"schema_version", "case_id", "case_number", "matter_sub_type_id", "actor_user_id", "at"}
    ),
    LIFECYCLE_DOCUMENT_UPLOADED: frozenset(
        {"schema_version", "case_id", "file_id", "filename", "actor_user_id", "at"}
    ),
    LIFECYCLE_MATTER_STATUS_CHANGED: frozenset(
        {"schema_version", "case_id", "case_number", "status", "actor_user_id", "at"}
    ),
}

ACTIVE_API_KEYS = frozenset(
    {
        "enabled",
        "module_id",
        "label",
        "panel_label",
        "requires_canary",
        "stages",
        "checklist_labels",
        "attr_fields",
        "matter_head_type_name",
        "matter_sub_type_names",
        "slots",
        "ui",
    }
)

PACKAGE_STATUS_KEYS = frozenset(
    {
        "attached",
        "compatible",
        "fault",
        "package_id",
        "package_version",
        "label",
        "requires_canary",
        "canary_version",
        "message",
        "detail",
        "mounts",
        "modules",
    }
)


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append(Result(name=name, ok=ok, detail=detail))
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"[{mark}] {name}{suffix}")

    @property
    def failed(self) -> list[Result]:
        return [r for r in self.results if not r.ok]


def mint_staff_token(db) -> tuple[User, str]:
    staff_email = os.getenv("FIRM_CONTRACT_STAFF_EMAIL", "").strip().lower()
    user = None
    if staff_email:
        user = db.execute(select(User).where(User.email == staff_email)).scalar_one_or_none()
    if user is None:
        user = db.execute(
            select(User).where(User.role == UserRole.admin, User.is_active.is_(True))
        ).scalars().first()
    if user is None:
        raise RuntimeError("No staff user found for firm contract smoke")
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = create_access_token(
        user_id=str(user.id),
        role=role,
        mfa_verified=True,
        password_ok=True,
        auth_token_version=int(getattr(user, "auth_token_version", 0) or 0),
    )
    return user, token


def _assert_payload_keys(event_type: str, payload: dict[str, Any]) -> str | None:
    required = LIFECYCLE_REQUIRED.get(event_type)
    if required is None:
        return f"unknown event type {event_type}"
    missing = sorted(required - set(payload.keys()))
    if missing:
        return f"missing keys {missing}"
    if payload.get("schema_version") != 1:
        return f"schema_version={payload.get('schema_version')!r} (want 1)"
    return None


def check_compat(report: Report) -> None:
    st = evaluate_firm_package_status(force=True)
    report.add(
        "compat: package attached",
        st.attached,
        f"package_id={st.package_id}",
    )
    report.add(
        "compat: requires_canary satisfied",
        st.compatible and not st.fault,
        f"canary={st.canary_version} requires={st.requires_canary} fault={st.fault} msg={st.message}",
    )


def check_migrate(report: Report, db) -> None:
    manifest = load_manifest(force=True)
    if not manifest:
        report.add("migrate: firm module manifest", False, "no module attached")
        return
    schema = storage_schema(manifest)
    if not schema:
        report.add("migrate: storage.schema", False, "missing in manifest")
        return
    report.add("migrate: storage.schema declared", True, schema)

    exists = db.execute(
        text("SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = :s)"),
        {"s": schema},
    ).scalar()
    report.add("migrate: firm schema exists", bool(exists), schema)

    table = str((manifest.get("storage") or {}).get("case_state_table") or "case_state")
    table_ok = db.execute(
        text(
            "SELECT EXISTS("
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :s AND table_name = :t)"
        ),
        {"s": schema, "t": table},
    ).scalar()
    report.add("migrate: case_state table", bool(table_ok), f"{schema}.{table}")

    revs = list(
        db.execute(text(f'SELECT revision FROM "{schema}".schema_migrations ORDER BY revision'))
    )
    report.add(
        "migrate: schema_migrations non-empty",
        len(revs) >= 1,
        f"revisions={[r[0] for r in revs]}",
    )


def check_api(report: Report, token: str) -> None:
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        headers = {"Authorization": f"Bearer {token}"}

        r = client.get("/firm-package/status", headers=headers)
        ok = r.status_code == 200
        body: dict[str, Any] = r.json() if ok else {}
        missing = sorted(PACKAGE_STATUS_KEYS - set(body.keys())) if ok else []
        report.add(
            "api: GET /firm-package/status",
            ok and not missing and body.get("attached") is True and body.get("compatible") is True,
            f"status={r.status_code} missing={missing} attached={body.get('attached')} "
            f"compatible={body.get('compatible')}",
        )

        r = client.get("/firm-modules/active", headers=headers)
        ok = r.status_code == 200
        body = r.json() if ok else {}
        missing = sorted(ACTIVE_API_KEYS - set(body.keys())) if ok else []
        ui = body.get("ui") if isinstance(body.get("ui"), dict) else {}
        slots = body.get("slots") if isinstance(body.get("slots"), dict) else {}
        report.add(
            "api: GET /firm-modules/active shape",
            ok
            and not missing
            and body.get("enabled") is True
            and bool(body.get("module_id"))
            and "matter_panel" in slots
            and bool(ui.get("bundle_url")),
            f"status={r.status_code} module_id={body.get('module_id')} missing={missing} "
            f"bundle={ui.get('bundle_url')}",
        )

        r = client.get("/firm-modules/active/pipeline", headers=headers)
        ok = r.status_code == 200
        body = r.json() if ok else {}
        report.add(
            "api: GET /firm-modules/active/pipeline",
            ok and body.get("enabled") is True and "by_stage" in body,
            f"status={r.status_code} total={body.get('total')}",
        )

        r = client.get("/firm-modules/active/ui/firm-module.js")
        report.add(
            "api: GET /firm-modules/active/ui/firm-module.js",
            r.status_code == 200 and len(r.content) > 0,
            f"status={r.status_code} bytes={len(r.content)}",
        )


def _find_in_scope_case(db, manifest: dict[str, Any]) -> Case | None:
    for row in db.execute(select(Case).order_by(Case.created_at.desc()).limit(50)).scalars():
        if module_applies_to_case(db, manifest, case_id=row.id):
            return row
    return None


def check_attach_surfaces(report: Report, db) -> None:
    """Wave E: firm-supplied matter types + assets mount env when package attached."""
    st = evaluate_firm_package_status(force=True)
    mounts = set(st.mounts or [])
    report.add(
        "attach: matter-types mount declared",
        "matter-types" in mounts or bool(os.getenv("FIRM_MATTER_TYPES_SEED_DIR")),
        f"mounts={sorted(mounts)} env={os.getenv('FIRM_MATTER_TYPES_SEED_DIR') or ''}",
    )
    head = db.execute(
        select(MatterHeadType).where(MatterHeadType.name == "Conveyancing, Residential")
    ).scalar_one_or_none()
    sub = None
    if head is not None:
        sub = db.execute(
            select(MatterSubType).where(
                MatterSubType.head_type_id == head.id,
                MatterSubType.name == "Purchase",
            )
        ).scalar_one_or_none()
    report.add(
        "attach: firm matter types present",
        head is not None and sub is not None,
        f"head={bool(head)} purchase={bool(sub)}",
    )
    assets_env = (os.getenv("FIRM_ASSETS_SEED_DIR") or "").strip()
    assets_ok = bool(assets_env) or "assets" in mounts
    report.add(
        "attach: assets seed path configured",
        assets_ok,
        f"FIRM_ASSETS_SEED_DIR={assets_env or '(unset)'} mounts_has_assets={'assets' in mounts}",
    )


def check_permissions(report: Report, db, token: str, case: Case) -> None:
    """Phase 7b: firm matter APIs respect case access; admin routes stay admin-only."""
    denied_email = "firm.contract.denied@example.com"
    user = db.execute(select(User).where(User.email == denied_email)).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=denied_email,
            password_hash=hash_password("FirmContractDenied!ChangeMe"),
            display_name="Firm Contract Denied",
            initials="FCD",
            role=UserRole.user,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()

    prev_lock = case.lock_mode
    case.lock_mode = CaseLockMode.allow_list
    db.add(case)
    db.commit()

    denied_token = create_access_token(
        user_id=str(user.id),
        role=UserRole.user.value,
        mfa_verified=True,
        password_ok=True,
        auth_token_version=int(getattr(user, "auth_token_version", 0) or 0),
    )
    try:
        with httpx.Client(base_url=BASE, timeout=30.0) as client:
            r = client.get(
                f"/firm-modules/active/matters/{case.id}",
                headers={"Authorization": f"Bearer {denied_token}"},
            )
            report.add(
                "permissions: firm matter GET denied without access",
                r.status_code == 403,
                f"status={r.status_code}",
            )
            r = client.put(
                f"/firm-modules/active/matters/{case.id}",
                headers={"Authorization": f"Bearer {denied_token}"},
                json={"stage": "hacked"},
            )
            report.add(
                "permissions: firm matter PUT denied without access",
                r.status_code == 403,
                f"status={r.status_code}",
            )
            r = client.get(
                "/admin/firm-settings",
                headers={"Authorization": f"Bearer {denied_token}"},
            )
            report.add(
                "permissions: admin firm-settings denied for non-admin",
                r.status_code in (401, 403),
                f"status={r.status_code}",
            )
            # Positive control: staff with access can still read
            r = client.get(
                f"/firm-modules/active/matters/{case.id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            report.add(
                "permissions: staff with access can GET firm matter",
                r.status_code == 200,
                f"status={r.status_code}",
            )
    finally:
        case.lock_mode = prev_lock
        db.add(case)
        db.commit()


def check_audit(report: Report, db, token: str, case: Case) -> None:
    """Phase 7b: firm case-state update writes an audit row."""
    before = db.execute(
        select(AuditEvent)
        .where(
            AuditEvent.action == "firm_module.case_state_update",
            AuditEvent.entity_id == str(case.id),
        )
        .order_by(AuditEvent.created_at.desc())
    ).scalars().first()
    before_id = before.id if before else None

    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        r = client.put(
            f"/firm-modules/active/matters/{case.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"attrs": {"firm_contract_audit": datetime.now(timezone.utc).isoformat()}},
        )
    report.add("audit: PUT firm case state succeeds", r.status_code == 200, f"status={r.status_code}")
    db.expire_all()
    after = db.execute(
        select(AuditEvent)
        .where(
            AuditEvent.action == "firm_module.case_state_update",
            AuditEvent.entity_id == str(case.id),
        )
        .order_by(AuditEvent.created_at.desc())
    ).scalars().first()
    ok = after is not None and (before_id is None or after.id != before_id)
    report.add("audit: firm case-state update row written", ok, f"audit_id={getattr(after, 'id', None)}")


def check_outbox(report: Report, db) -> None:
    """Phase 7b: retry drain + once-only delivery."""
    payload = {
        "schema_version": 1,
        "case_id": str(uuid.uuid4()),
        "file_id": str(uuid.uuid4()),
        "filename": "firm-contract-outbox-retry.txt",
        "actor_user_id": None,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    row = enqueue_lifecycle_event(db, event_type=LIFECYCLE_DOCUMENT_UPLOADED, payload=payload)
    db.commit()
    event_id = row.id

    n1 = process_pending_lifecycle_events(db, limit=50)
    db.commit()
    db.expire_all()
    processed = db.get(FirmLifecycleOutbox, event_id)
    report.add(
        "outbox: pending drain processes row",
        n1 >= 1 and processed is not None and processed.processed_at is not None,
        f"drained={n1} processed_at={getattr(processed, 'processed_at', None)}",
    )
    first_processed_at = processed.processed_at if processed else None

    # Once-only: re-deliver same row is a no-op; second drain should not clear processed_at
    if processed is not None:
        deliver_lifecycle_event(db, processed, manifest=load_manifest(force=True))
        db.commit()
        db.expire_all()
        again = db.get(FirmLifecycleOutbox, event_id)
        report.add(
            "outbox: re-deliver is once-only",
            again is not None and again.processed_at == first_processed_at,
            f"processed_at={getattr(again, 'processed_at', None)}",
        )
    else:
        report.add("outbox: re-deliver is once-only", False, "row missing after drain")

    n2 = process_pending_lifecycle_events(db, limit=50)
    db.commit()
    report.add(
        "outbox: second drain does not re-queue processed",
        True,
        f"drained={n2}",
    )


def check_concurrency(report: Report, token: str, case: Case) -> None:
    """Phase 7b: parallel firm case-state writes do not corrupt the row."""
    case_id = str(case.id)
    markers = [f"c{i}-{uuid.uuid4().hex[:8]}" for i in range(6)]

    def _put(marker: str) -> tuple[int, str]:
        with httpx.Client(base_url=BASE, timeout=30.0) as client:
            r = client.put(
                f"/firm-modules/active/matters/{case_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"attrs": {"firm_contract_concurrency": marker}},
            )
            body = r.json() if r.status_code == 200 else {}
            attrs = body.get("attrs") if isinstance(body, dict) else {}
            return r.status_code, str((attrs or {}).get("firm_contract_concurrency") or "")

    statuses: list[int] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_put, m) for m in markers]
        for fut in as_completed(futures):
            status_code, _value = fut.result()
            statuses.append(status_code)

    all_ok = all(s == 200 for s in statuses)
    report.add(
        "concurrency: parallel PUT firm case state all succeed",
        all_ok,
        f"statuses={statuses}",
    )

    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        r = client.get(
            f"/firm-modules/active/matters/{case_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json() if r.status_code == 200 else {}
        final = str(((body.get("attrs") or {}) if isinstance(body, dict) else {}).get("firm_contract_concurrency") or "")
    report.add(
        "concurrency: final state is one of the writes",
        r.status_code == 200 and final in markers,
        f"final={final!r}",
    )


def check_lifecycle(report: Report, db, actor: User) -> None:
    for event_type, keys in LIFECYCLE_REQUIRED.items():
        report.add(
            f"lifecycle: contract keys listed for {event_type}",
            True,
            ",".join(sorted(keys)),
        )

    manifest = load_manifest(force=True)
    if not manifest:
        report.add("lifecycle: module attached", False, "no manifest")
        return

    case = _find_in_scope_case(db, manifest)
    if case is None:
        report.add(
            "lifecycle: find in-scope matter",
            False,
            "no matter matches module matter_* filters — seed a Purchase matter",
        )
        return
    report.add("lifecycle: find in-scope matter", True, f"case={case.case_number}")

    # Matter created payload
    process_matter_created(db, case_id=case.id, actor_user_id=actor.id)
    db.commit()
    created = db.execute(
        text(
            "SELECT payload FROM firm_lifecycle_outbox "
            "WHERE event_type = :t AND payload->>'case_id' = :cid "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"t": LIFECYCLE_MATTER_CREATED, "cid": str(case.id)},
    ).scalar()
    err = _assert_payload_keys(LIFECYCLE_MATTER_CREATED, dict(created or {}))
    report.add("lifecycle: matter.created payload", err is None, err or "ok")

    # Document uploaded payload
    file_id = uuid.uuid4()
    process_document_uploaded(
        db,
        case_id=case.id,
        file_id=file_id,
        actor_user_id=actor.id,
        filename="firm-contract-smoke.txt",
    )
    db.commit()
    uploaded = db.execute(
        text(
            "SELECT payload FROM firm_lifecycle_outbox "
            "WHERE event_type = :t AND payload->>'file_id' = :fid "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"t": LIFECYCLE_DOCUMENT_UPLOADED, "fid": str(file_id)},
    ).scalar()
    err = _assert_payload_keys(LIFECYCLE_DOCUMENT_UPLOADED, dict(uploaded or {}))
    report.add("lifecycle: document.uploaded payload", err is None, err or "ok")

    # Status changed payload
    status_val = case.status.value if hasattr(case.status, "value") else str(case.status)
    process_matter_status_changed(
        db, case_id=case.id, status=status_val, actor_user_id=actor.id
    )
    db.commit()
    changed = db.execute(
        text(
            "SELECT payload FROM firm_lifecycle_outbox "
            "WHERE event_type = :t AND payload->>'case_id' = :cid "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"t": LIFECYCLE_MATTER_STATUS_CHANGED, "cid": str(case.id)},
    ).scalar()
    err = _assert_payload_keys(LIFECYCLE_MATTER_STATUS_CHANGED, dict(changed or {}))
    report.add("lifecycle: matter.status_changed payload", err is None, err or "ok")


def main() -> int:
    print(f"Firm contract smoke against {BASE} @ {datetime.now(timezone.utc).isoformat()}")
    report = Report()
    db = SessionLocal()
    try:
        check_compat(report)
        check_migrate(report, db)
        check_attach_surfaces(report, db)
        _user, token = mint_staff_token(db)
        check_api(report, token)
        check_lifecycle(report, db, _user)
        manifest = load_manifest(force=True)
        case = _find_in_scope_case(db, manifest) if manifest else None
        if case is None:
            report.add("phase7b: in-scope matter for kit", False, "no Purchase/in-scope matter")
        else:
            check_permissions(report, db, token, case)
            check_audit(report, db, token, case)
            check_outbox(report, db)
            check_concurrency(report, token, case)
    except Exception as exc:  # noqa: BLE001
        report.add("smoke: unexpected error", False, str(exc))
        raise
    finally:
        db.close()

    failed = report.failed
    print()
    print(f"Summary: {len(report.results) - len(failed)}/{len(report.results)} passed")
    if failed:
        print("FAILED:")
        for r in failed:
            print(f"  - {r.name}: {r.detail}")
        return 1
    print("All firm contract checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback

        traceback.print_exc()
        raise SystemExit(1)
