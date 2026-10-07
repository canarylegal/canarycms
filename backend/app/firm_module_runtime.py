"""Load firm-module manifests from ``FIRM_MODULE_DIR`` and apply lifecycle reactions.

Phase 5: firm case state lives in a firm Postgres schema; core keeps the lifecycle
outbox. Firm UI is a build-time bundle under ``module/ui/dist``.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, FirmLifecycleOutbox, FirmModuleCaseState, MatterHeadType, MatterSubType
from app.models.case_matter import CaseStatus
from app.models.firm_module import FIRM_EXAMPLE_PILOT_SCHEMA

log = logging.getLogger(__name__)

# Published lifecycle event types (versioned contract — do not rename silently).
LIFECYCLE_MATTER_CREATED = "lifecycle.matter.created"
LIFECYCLE_DOCUMENT_UPLOADED = "lifecycle.document.uploaded"
LIFECYCLE_MATTER_STATUS_CHANGED = "lifecycle.matter.status_changed"
LIFECYCLE_MATTER_UPDATED = "lifecycle.matter.updated"  # reserved
LIFECYCLE_MATTER_CLOSED = "lifecycle.matter.closed"  # reserved alias; use status_changed
LIFECYCLE_PORTAL_GRANT_CREATED = "lifecycle.portal.grant_created"  # stub — not wired yet

# Matter statuses excluded from the firm pipeline dashboard (no hard-delete in product).
_PIPELINE_INACTIVE_STATUSES = frozenset(
    {
        CaseStatus.closed,
        CaseStatus.archived,
        CaseStatus.quote_closed,
    }
)

# Published UI / action slot ids (versioned contract).
SLOT_MATTER_PANEL = "matter_panel"
SLOT_DASHBOARD_WIDGET = "dashboard_widget"
SLOT_MATTER_ACTIONS = "matter_actions"
SLOT_PORTAL_SECTION = "portal_section"
SLOT_ADMIN_PAGE = "admin_page"

_ALL_SLOTS = (
    SLOT_MATTER_PANEL,
    SLOT_DASHBOARD_WIDGET,
    SLOT_MATTER_ACTIONS,
    SLOT_PORTAL_SECTION,
    SLOT_ADMIN_PAGE,
)

_manifest_cache: dict[str, Any] | None = None
_manifest_mtime: float | None = None


def firm_module_dir() -> Path | None:
    raw = (os.getenv("FIRM_MODULE_DIR") or "").strip()
    if not raw:
        # Convention when firm package is mounted at /firm
        candidate = Path("/firm/module")
        return candidate if candidate.is_dir() else None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def load_manifest(*, force: bool = False) -> dict[str, Any] | None:
    """Return module manifest or None if no firm module is attached / package incompatible."""
    global _manifest_cache, _manifest_mtime
    # Phase 6: refuse module when package-level requires_canary fails.
    from app.firm_package import firm_package_allows_module

    if not firm_package_allows_module(force=force):
        _manifest_cache = None
        _manifest_mtime = None
        return None
    directory = firm_module_dir()
    if directory is None:
        _manifest_cache = None
        _manifest_mtime = None
        return None
    path = directory / "manifest.json"
    if not path.is_file():
        return None
    mtime = path.stat().st_mtime
    if not force and _manifest_cache is not None and _manifest_mtime == mtime:
        return _manifest_cache
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        log.warning("Unsupported firm module manifest version: %s", raw.get("version"))
        return None
    module_id = (raw.get("module_id") or "").strip()
    if not module_id:
        log.warning("Firm module manifest missing module_id")
        return None
    _manifest_cache = raw
    _manifest_mtime = mtime
    return raw


def ui_section(manifest: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return the ``ui`` block from the active (or given) manifest, if present."""
    m = manifest if manifest is not None else load_manifest()
    if not m:
        return None
    ui = m.get("ui")
    return ui if isinstance(ui, dict) else None


def storage_schema(manifest: dict[str, Any] | None = None) -> str | None:
    """Firm Postgres schema name from manifest ``storage.schema`` (Phase 5)."""
    m = manifest if manifest is not None else load_manifest()
    if not m:
        return None
    storage = m.get("storage") if isinstance(m.get("storage"), dict) else {}
    raw = str(storage.get("schema") or "").strip()
    return raw or None


def _assert_storage_schema(manifest: dict[str, Any]) -> None:
    """Pilot ORM is bound to ``firm_example_pilot``; manifest must agree."""
    schema = storage_schema(manifest)
    if schema and schema != FIRM_EXAMPLE_PILOT_SCHEMA:
        raise RuntimeError(
            f"Firm storage.schema={schema!r} is not supported by this Canary build "
            f"(expected {FIRM_EXAMPLE_PILOT_SCHEMA!r} for example_pilot)"
        )


def resolve_ui_asset(rel_path: str) -> Path | None:
    """Resolve a path under the firm module UI dist, refusing path traversal."""
    directory = firm_module_dir()
    if directory is None:
        return None
    ui = ui_section()
    # Default layout: module/ui/dist/
    bundle_rel = ""
    if ui and isinstance(ui.get("bundle"), str) and ui["bundle"].strip():
        bundle_rel = ui["bundle"].strip().lstrip("/")
    base = (directory / Path(bundle_rel).parent) if bundle_rel else (directory / "ui" / "dist")
    try:
        base_resolved = base.resolve()
    except OSError:
        return None
    if not base_resolved.is_dir():
        return None
    candidate = (base_resolved / rel_path.lstrip("/")).resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def slots_enabled(manifest: dict[str, Any]) -> dict[str, bool]:
    """Which published slots this module claims (defaults: panel + dashboard if UI present)."""
    ui = ui_section(manifest) or {}
    exports = ui.get("exports") if isinstance(ui.get("exports"), dict) else {}
    declared = manifest.get("slots")
    out: dict[str, bool] = {s: False for s in _ALL_SLOTS}
    if isinstance(declared, dict):
        for key in _ALL_SLOTS:
            if key in declared:
                out[key] = bool(declared[key])
        return out
    # Infer from ui.exports when slots block omitted
    out[SLOT_MATTER_PANEL] = bool(exports.get(SLOT_MATTER_PANEL) or exports.get("matter_panel"))
    out[SLOT_DASHBOARD_WIDGET] = bool(exports.get(SLOT_DASHBOARD_WIDGET) or exports.get("dashboard_widget"))
    out[SLOT_MATTER_ACTIONS] = bool(exports.get(SLOT_MATTER_ACTIONS))
    out[SLOT_PORTAL_SECTION] = bool(exports.get(SLOT_PORTAL_SECTION))
    out[SLOT_ADMIN_PAGE] = bool(exports.get(SLOT_ADMIN_PAGE))
    # Legacy Phase 3 manifests without ui.exports still get panel + dashboard
    if not ui and not isinstance(declared, dict):
        out[SLOT_MATTER_PANEL] = True
        out[SLOT_DASHBOARD_WIDGET] = True
    return out


def module_applies_to_case(db: Session, manifest: dict[str, Any], *, case_id: uuid.UUID) -> bool:
    from app.models import Case

    case = db.get(Case, case_id)
    if case is None or not case.matter_sub_type_id:
        return False
    sub = db.get(MatterSubType, case.matter_sub_type_id)
    if sub is None:
        return False
    head = db.get(MatterHeadType, sub.head_type_id)
    head_want = (manifest.get("matter_head_type_name") or "").strip()
    if head_want and (not head or head.name != head_want):
        return False
    subs = manifest.get("matter_sub_type_names") or []
    if subs and sub.name not in subs:
        return False
    return True


def _default_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    stages = [str(s) for s in (manifest.get("stages") or []) if str(s).strip()]
    checklist = [
        {"key": f"item_{i}", "label": str(label), "done": False}
        for i, label in enumerate(manifest.get("checklist") or [])
        if str(label).strip()
    ]
    attrs = {str(f.get("key")): "" for f in (manifest.get("attr_fields") or []) if f.get("key")}
    return {
        "stage": stages[0] if stages else "",
        "stages": stages,
        "checklist": checklist,
        "attrs": attrs,
        "pipeline_active": True,
        "integration": {"stub": (manifest.get("integration_stub") or "log_only"), "last_event": None},
    }


def ensure_case_state(db: Session, *, module_id: str, case_id: uuid.UUID, manifest: dict[str, Any]) -> FirmModuleCaseState:
    _assert_storage_schema(manifest)
    row = db.execute(
        select(FirmModuleCaseState).where(
            FirmModuleCaseState.module_id == module_id,
            FirmModuleCaseState.case_id == case_id,
        )
    ).scalar_one_or_none()
    if row:
        return row
    now = datetime.now(timezone.utc)
    row = FirmModuleCaseState(
        id=uuid.uuid4(),
        module_id=module_id,
        case_id=case_id,
        payload=_default_payload(manifest),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def enqueue_lifecycle_event(
    db: Session,
    *,
    event_type: str,
    payload: dict[str, Any],
) -> FirmLifecycleOutbox:
    """Write a lifecycle notification in the **same transaction** as the business change."""
    row = FirmLifecycleOutbox(
        id=uuid.uuid4(),
        event_type=event_type,
        payload=payload,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def deliver_lifecycle_event(
    db: Session,
    outbox: FirmLifecycleOutbox,
    *,
    manifest: dict[str, Any] | None = None,
) -> None:
    """Deliver one outbox row (idempotent if already processed).

    Phase 4: sync ``log_only`` stub. Async worker with retries can call the same
    helper later without changing the enqueue contract.
    """
    if outbox.processed_at is not None:
        return
    m = manifest or load_manifest()
    stub = ((m or {}).get("integration_stub") or "log_only").strip() or "log_only"
    module_id = str((m or {}).get("module_id") or "unknown")
    try:
        if stub == "log_only":
            log.info(
                "firm_module %s integration stub handled %s payload=%s",
                module_id,
                outbox.event_type,
                outbox.payload,
            )
        else:
            log.warning(
                "firm_module %s unknown integration_stub=%s for %s — leaving unprocessed",
                module_id,
                stub,
                outbox.event_type,
            )
            outbox.error = f"unknown integration_stub: {stub}"
            db.add(outbox)
            return
        outbox.processed_at = datetime.now(timezone.utc)
        outbox.error = None
        db.add(outbox)
    except Exception as exc:  # noqa: BLE001 — record and leave for retry
        outbox.error = str(exc)[:2000]
        db.add(outbox)
        log.exception("firm_module lifecycle delivery failed event=%s", outbox.event_type)


def process_pending_lifecycle_events(db: Session, *, limit: int = 50) -> int:
    """Drain unprocessed outbox rows (async-delivery entry point). Returns count delivered."""
    manifest = load_manifest()
    rows = (
        db.execute(
            select(FirmLifecycleOutbox)
            .where(FirmLifecycleOutbox.processed_at.is_(None))
            .order_by(FirmLifecycleOutbox.created_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    for row in rows:
        deliver_lifecycle_event(db, row, manifest=manifest)
    return len(rows)


def process_matter_created(db: Session, *, case_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
    """Seed firm module state for matching matters; enqueue + deliver lifecycle.matter.created.

    Enqueue happens in the caller's transaction (same as case create). Delivery is sync
    for the ``log_only`` stub; ``process_pending_lifecycle_events`` is the async path.
    """
    manifest = load_manifest()
    if not manifest:
        return
    module_id = str(manifest["module_id"])
    if not module_applies_to_case(db, manifest, case_id=case_id):
        return

    case = db.get(Case, case_id)
    event_payload = {
        "schema_version": 1,
        "case_id": str(case_id),
        "case_number": case.case_number if case else None,
        "matter_sub_type_id": str(case.matter_sub_type_id) if case and case.matter_sub_type_id else None,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    outbox = enqueue_lifecycle_event(db, event_type=LIFECYCLE_MATTER_CREATED, payload=event_payload)
    state = ensure_case_state(db, module_id=module_id, case_id=case_id, manifest=manifest)
    integ = dict(state.payload.get("integration") or {})
    stub = (manifest.get("integration_stub") or "log_only").strip() or "log_only"
    integ["stub"] = stub
    integ["last_event"] = event_payload
    state.payload = {**state.payload, "integration": integ}
    state.updated_at = datetime.now(timezone.utc)
    db.add(state)
    deliver_lifecycle_event(db, outbox, manifest=manifest)


def process_document_uploaded(
    db: Session,
    *,
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    filename: str | None = None,
) -> None:
    """Enqueue lifecycle.document.uploaded when a firm module is attached (scope-agnostic).

    Published stub: always enqueues when a module is mounted; firm code decides relevance.
    """
    manifest = load_manifest()
    if not manifest:
        return
    event_payload = {
        "schema_version": 1,
        "case_id": str(case_id),
        "file_id": str(file_id),
        "filename": filename,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    outbox = enqueue_lifecycle_event(db, event_type=LIFECYCLE_DOCUMENT_UPLOADED, payload=event_payload)
    deliver_lifecycle_event(db, outbox, manifest=manifest)


def process_matter_status_changed(
    db: Session,
    *,
    case_id: uuid.UUID,
    status: str,
    actor_user_id: uuid.UUID | None,
) -> None:
    """React to matter status changes (closed/archived/…). No hard-delete in the product.

    Marks firm case state ``pipeline_active`` and enqueues ``lifecycle.matter.status_changed``.
    """
    manifest = load_manifest()
    if not manifest:
        return
    module_id = str(manifest["module_id"])
    case = db.get(Case, case_id)
    event_payload = {
        "schema_version": 1,
        "case_id": str(case_id),
        "case_number": case.case_number if case else None,
        "status": status,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    outbox = enqueue_lifecycle_event(db, event_type=LIFECYCLE_MATTER_STATUS_CHANGED, payload=event_payload)

    if module_applies_to_case(db, manifest, case_id=case_id):
        try:
            state = ensure_case_state(db, module_id=module_id, case_id=case_id, manifest=manifest)
        except Exception:
            log.exception("firm_module status change: could not load case state case=%s", case_id)
            deliver_lifecycle_event(db, outbox, manifest=manifest)
            return
        try:
            status_enum = CaseStatus(status)
        except ValueError:
            status_enum = None
        active = status_enum is None or status_enum not in _PIPELINE_INACTIVE_STATUSES
        data = dict(state.payload or {})
        data["pipeline_active"] = active
        integ = dict(data.get("integration") or {})
        integ["last_event"] = event_payload
        data["integration"] = integ
        state.payload = data
        state.updated_at = datetime.now(timezone.utc)
        db.add(state)

    deliver_lifecycle_event(db, outbox, manifest=manifest)


def pipeline_summary(db: Session, manifest: dict[str, Any]) -> dict[str, Any]:
    """Count active Purchase matters by stage (excludes closed/archived/quote_closed)."""
    _assert_storage_schema(manifest)
    module_id = str(manifest["module_id"])
    stages = [str(s) for s in (manifest.get("stages") or []) if str(s).strip()]
    rows = db.execute(
        select(FirmModuleCaseState, Case.status)
        .outerjoin(Case, Case.id == FirmModuleCaseState.case_id)
        .where(FirmModuleCaseState.module_id == module_id)
    ).all()
    by_stage = {s: 0 for s in stages}
    unstaged = 0
    total = 0
    for row, case_status in rows:
        payload = row.payload or {}
        if payload.get("pipeline_active") is False:
            continue
        if case_status in _PIPELINE_INACTIVE_STATUSES:
            continue
        total += 1
        stage = str(payload.get("stage") or "").strip()
        if stage in by_stage:
            by_stage[stage] += 1
        else:
            unstaged += 1
    return {
        "module_id": module_id,
        "label": (manifest.get("label") or module_id),
        "by_stage": by_stage,
        "unstaged": unstaged,
        "total": total,
    }
