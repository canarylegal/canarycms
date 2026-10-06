"""Optional firm portal-form templates from ``PORTAL_FORMS_SEED_DIR``.

Looks for ``manifest.json`` under ``PORTAL_FORMS_SEED_DIR`` (unset = skip).
On every startup, imports any template whose ``reference`` is not yet in the database.
Existing templates are left unchanged (admin edits win). Set
``PORTAL_FORMS_SEED_REPAIR=1`` to refresh fields on existing rows from the seed.

Manifest version 1::

    {
      "version": 1,
      "templates": [
        {
          "reference": "example_form",
          "name": "Example Form",
          "description": "...",
          "scope": "global" | "residential_purchase" | "residential_sale"
                   | {"matter_head_type_name": "...", "matter_sub_type_name": "..."} ,
          "fields": [ { "field_key", "label", "field_type", ... }, ... ]
        }
      ]
    }

``scope`` string shortcuts match common conveyancing matter types from the product seed.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_access import user_effective_admin
from app.models import MatterHeadType, MatterSubType, PortalFormTemplate, User
from app.portal_form_service import _apply_fields, create_template

log = logging.getLogger(__name__)

def _seed_dir_from_env() -> Path | None:
    raw = (os.getenv("PORTAL_FORMS_SEED_DIR") or "").strip()
    return Path(raw).expanduser() if raw else None


def _first_admin(db: Session) -> User | None:
    for row in db.execute(select(User).order_by(User.created_at.asc())).scalars().all():
        if user_effective_admin(row, db):
            return row
    return None


def _load_manifest(seed_dir: Path) -> dict[str, Any] | None:
    manifest_path = seed_dir / "manifest.json"
    if not manifest_path.is_file():
        log.info("No portal forms seed manifest at %s — skipping.", manifest_path)
        return None
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        log.warning("Unsupported portal forms seed version: %s", raw.get("version"))
        return None
    return raw


def _resolve_scope(
    db: Session, scope: Any
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    if scope is None or scope == "global":
        return None, None
    if isinstance(scope, dict):
        head_name = (scope.get("matter_head_type_name") or "").strip()
        sub_name = (scope.get("matter_sub_type_name") or "").strip() or None
    else:
        key = str(scope).strip()
        if key == "residential_purchase":
            head_name, sub_name = "Conveyancing, Residential", "Purchase"
        elif key == "residential_sale":
            head_name, sub_name = "Conveyancing, Residential", "Sale"
        elif key == "residential_head":
            head_name, sub_name = "Conveyancing, Residential", None
        else:
            log.warning("Portal forms seed: unknown scope %r — treating as global.", key)
            return None, None

    if not head_name:
        return None, None
    head = db.execute(select(MatterHeadType).where(MatterHeadType.name == head_name)).scalar_one_or_none()
    if head is None:
        raise RuntimeError(f"Portal forms seed: matter head type not found: {head_name}")
    if not sub_name:
        return head.id, None
    sub = db.execute(
        select(MatterSubType).where(
            MatterSubType.head_type_id == head.id,
            MatterSubType.name == sub_name,
        )
    ).scalar_one_or_none()
    if sub is None:
        raise RuntimeError(f"Portal forms seed: matter sub type not found: {head_name} / {sub_name}")
    return head.id, sub.id


def sync_portal_forms_from_seed(db: Session, *, seed_dir: Path | None = None) -> int:
    """Import missing portal form templates from seed. Returns count created (or repaired)."""
    directory = Path(seed_dir) if seed_dir is not None else _seed_dir_from_env()
    if directory is None:
        return 0
    raw = _load_manifest(directory)
    if raw is None:
        return 0

    owner = _first_admin(db)
    if owner is None:
        log.warning("No admin user — cannot apply portal forms seed.")
        return 0

    repair = os.getenv("PORTAL_FORMS_SEED_REPAIR", "").strip().lower() in ("1", "true", "yes")
    created = 0
    repaired = 0
    try:
        for spec in raw.get("templates") or []:
            ref = (spec.get("reference") or "").strip()
            if not ref:
                continue
            existing = db.execute(
                select(PortalFormTemplate).where(PortalFormTemplate.reference == ref)
            ).scalar_one_or_none()
            head_id, sub_id = _resolve_scope(db, spec.get("scope"))
            fields = list(spec.get("fields") or [])
            if existing:
                if not repair:
                    continue
                existing.name = str(spec.get("name") or existing.name).strip()[:300]
                existing.description = (
                    str(spec["description"]).strip() if spec.get("description") else None
                )
                existing.matter_head_type_id = head_id
                existing.matter_sub_type_id = sub_id
                if fields:
                    _apply_fields(db, existing.id, fields)
                repaired += 1
                continue
            create_template(
                db,
                payload={
                    "name": str(spec.get("name") or ref).strip()[:300],
                    "reference": ref,
                    "description": str(spec["description"]).strip() if spec.get("description") else None,
                    "matter_head_type_id": head_id,
                    "matter_sub_type_id": sub_id,
                    "fields": fields,
                },
                owner=owner,
            )
            created += 1
        if created or repaired:
            db.commit()
            log.info(
                "Portal forms seed from %s: created %s, repaired %s.",
                directory / "manifest.json",
                created,
                repaired,
            )
    except Exception:
        db.rollback()
        raise
    return created + repaired
