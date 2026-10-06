"""Load firm-module manifests from ``FIRM_MODULE_DIR`` and apply lifecycle reactions.

Phase 3 pilot: config-driven modules (JSON), not arbitrary in-process plugin code.
Candidate Phase 4: published slots + versioned event payloads.
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

from app.models import FirmLifecycleOutbox, FirmModuleCaseState, MatterHeadType, MatterSubType

log = logging.getLogger(__name__)

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
    """Return module manifest or None if no firm module is attached."""
    global _manifest_cache, _manifest_mtime
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
        "integration": {"stub": (manifest.get("integration_stub") or "log_only"), "last_event": None},
    }


def ensure_case_state(db: Session, *, module_id: str, case_id: uuid.UUID, manifest: dict[str, Any]) -> FirmModuleCaseState:
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
    row = FirmLifecycleOutbox(
        id=uuid.uuid4(),
        event_type=event_type,
        payload=payload,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def process_matter_created(db: Session, *, case_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
    """Seed firm module state for matching matters; mark outbox processed (sync pilot)."""
    manifest = load_manifest()
    if not manifest:
        return
    module_id = str(manifest["module_id"])
    if not module_applies_to_case(db, manifest, case_id=case_id):
        return

    from app.models import Case

    case = db.get(Case, case_id)
    event_payload = {
        "case_id": str(case_id),
        "case_number": case.case_number if case else None,
        "matter_sub_type_id": str(case.matter_sub_type_id) if case and case.matter_sub_type_id else None,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    outbox = enqueue_lifecycle_event(db, event_type="lifecycle.matter.created", payload=event_payload)
    state = ensure_case_state(db, module_id=module_id, case_id=case_id, manifest=manifest)
    integ = dict(state.payload.get("integration") or {})
    stub = (manifest.get("integration_stub") or "log_only").strip() or "log_only"
    integ["stub"] = stub
    integ["last_event"] = event_payload
    state.payload = {**state.payload, "integration": integ}
    state.updated_at = datetime.now(timezone.utc)
    db.add(state)
    # Pilot: sync "delivery" — log-only integration stub
    if stub == "log_only":
        log.info(
            "firm_module %s integration stub handled lifecycle.matter.created case=%s",
            module_id,
            case_id,
        )
    outbox.processed_at = datetime.now(timezone.utc)
    db.add(outbox)


def pipeline_summary(db: Session, manifest: dict[str, Any]) -> dict[str, Any]:
    """Count open Purchase matters by stage for the dashboard widget."""
    module_id = str(manifest["module_id"])
    stages = [str(s) for s in (manifest.get("stages") or []) if str(s).strip()]
    rows = db.execute(
        select(FirmModuleCaseState).where(FirmModuleCaseState.module_id == module_id)
    ).scalars().all()
    by_stage = {s: 0 for s in stages}
    unstaged = 0
    for row in rows:
        stage = str((row.payload or {}).get("stage") or "").strip()
        if stage in by_stage:
            by_stage[stage] += 1
        else:
            unstaged += 1
    return {
        "module_id": module_id,
        "label": (manifest.get("label") or module_id),
        "by_stage": by_stage,
        "unstaged": unstaged,
        "total": len(rows),
    }
