"""Optional firm fee-scale templates from ``FEE_SCALES_SEED_DIR``.

Looks for ``manifest.json`` under the env dir (unset = skip).
On every startup, imports any scale whose ``reference`` is not yet in the database.
Existing scales are left unchanged (admin edits win). Set
``FEE_SCALES_SEED_REPAIR=1`` to replace categories/lines/bands on existing rows.

Manifest version 1::

    {
      "version": 1,
      "scales": [
        {
          "reference": "example_purchase",
          "name": "Residential purchase",
          "vat_rate_bps": 2000,
          "scope": "residential_purchase" | "global" | {
            "matter_head_type_name": "...",
            "matter_sub_type_name": "..."
          },
          "band_sets": [
            {
              "key": "legal_fee",
              "name": "Legal fee by price",
              "rows": [
                {"min_value_pence": 0, "max_value_pence": 50000000, "amount_pence": 99500},
                {"min_value_pence": 50000001, "max_value_pence": null, "amount_pence": 129500}
              ]
            }
          ],
          "categories": [
            {
              "name": "Legal fees",
              "lines": [
                {
                  "name": "Legal fee",
                  "line_kind": "item",
                  "amount_kind": "band",
                  "band_set_key": "legal_fee",
                  "vat_treatment": "plus_vat"
                },
                {"name": "Subtotal", "line_kind": "subtotal"},
                {"name": "VAT", "line_kind": "vat"},
                {"name": "Total", "line_kind": "total"}
              ]
            }
          ]
        }
      ]
    }
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

from app.admin_access import user_effective_admin
from app.models import (
    FeeScale,
    FeeScaleAmountKind,
    FeeScaleBandRow,
    FeeScaleBandSet,
    FeeScaleCategory,
    FeeScaleLine,
    FeeScaleLineKind,
    FeeScaleVatTreatment,
    MatterHeadType,
    MatterSubType,
    User,
)

log = logging.getLogger(__name__)


def _seed_dir_from_env() -> Path | None:
    raw = (os.getenv("FEE_SCALES_SEED_DIR") or "").strip()
    return Path(raw).expanduser() if raw else None


def _first_admin(db: Session) -> User | None:
    for row in db.execute(select(User).order_by(User.created_at.asc())).scalars().all():
        if user_effective_admin(row, db):
            return row
    return None


def _load_manifest(seed_dir: Path) -> dict[str, Any] | None:
    manifest_path = seed_dir / "manifest.json"
    if not manifest_path.is_file():
        log.info("No fee scales seed manifest at %s — skipping.", manifest_path)
        return None
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        log.warning("Unsupported fee scales seed version: %s", raw.get("version"))
        return None
    return raw


def _resolve_scope(db: Session, scope: Any) -> tuple[uuid.UUID | None, uuid.UUID | None]:
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
            log.warning("Fee scales seed: unknown scope %r — treating as global.", key)
            return None, None

    if not head_name:
        return None, None
    head = db.execute(select(MatterHeadType).where(MatterHeadType.name == head_name)).scalar_one_or_none()
    if head is None:
        raise RuntimeError(f"Fee scales seed: matter head type not found: {head_name}")
    if not sub_name:
        return head.id, None
    sub = db.execute(
        select(MatterSubType).where(
            MatterSubType.head_type_id == head.id,
            MatterSubType.name == sub_name,
        )
    ).scalar_one_or_none()
    if sub is None:
        raise RuntimeError(f"Fee scales seed: matter sub type not found: {head_name} / {sub_name}")
    return head.id, sub.id


def _clear_scale_children(db: Session, scale_id: uuid.UUID) -> None:
    cats = db.execute(select(FeeScaleCategory).where(FeeScaleCategory.fee_scale_id == scale_id)).scalars().all()
    for cat in cats:
        for line in db.execute(select(FeeScaleLine).where(FeeScaleLine.category_id == cat.id)).scalars().all():
            db.delete(line)
        db.delete(cat)
    sets = db.execute(select(FeeScaleBandSet).where(FeeScaleBandSet.fee_scale_id == scale_id)).scalars().all()
    for bs in sets:
        for row in db.execute(select(FeeScaleBandRow).where(FeeScaleBandRow.band_set_id == bs.id)).scalars().all():
            db.delete(row)
        db.delete(bs)
    db.flush()


def _apply_scale_body(db: Session, scale: FeeScale, spec: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    band_key_to_id: dict[str, uuid.UUID] = {}
    for i, bs_spec in enumerate(spec.get("band_sets") or []):
        key = str(bs_spec.get("key") or bs_spec.get("name") or f"band_{i}").strip()
        bs = FeeScaleBandSet(
            id=uuid.uuid4(),
            fee_scale_id=scale.id,
            name=str(bs_spec.get("name") or key).strip()[:200],
            sort_order=int(bs_spec.get("sort_order") if bs_spec.get("sort_order") is not None else i),
            created_at=now,
            updated_at=now,
        )
        db.add(bs)
        db.flush()
        band_key_to_id[key] = bs.id
        for j, row_spec in enumerate(bs_spec.get("rows") or []):
            max_raw = row_spec.get("max_value_pence")
            db.add(
                FeeScaleBandRow(
                    id=uuid.uuid4(),
                    band_set_id=bs.id,
                    min_value_pence=int(row_spec.get("min_value_pence") or 0),
                    max_value_pence=int(max_raw) if max_raw is not None else None,
                    amount_pence=int(row_spec.get("amount_pence") or 0),
                    sort_order=int(row_spec.get("sort_order") if row_spec.get("sort_order") is not None else j),
                    created_at=now,
                    updated_at=now,
                )
            )

    for i, cat_spec in enumerate(spec.get("categories") or []):
        cat = FeeScaleCategory(
            id=uuid.uuid4(),
            fee_scale_id=scale.id,
            name=str(cat_spec.get("name") or f"Category {i + 1}").strip()[:200],
            sort_order=int(cat_spec.get("sort_order") if cat_spec.get("sort_order") is not None else i),
            created_at=now,
            updated_at=now,
        )
        db.add(cat)
        db.flush()
        for j, line_spec in enumerate(cat_spec.get("lines") or []):
            line_kind = FeeScaleLineKind(str(line_spec.get("line_kind") or "item"))
            amount_kind_raw = line_spec.get("amount_kind")
            amount_kind = FeeScaleAmountKind(str(amount_kind_raw)) if amount_kind_raw else None
            band_set_id = None
            band_key = (line_spec.get("band_set_key") or "").strip()
            if band_key:
                band_set_id = band_key_to_id.get(band_key)
                if band_set_id is None:
                    raise RuntimeError(f"Fee scales seed: unknown band_set_key {band_key!r} on {scale.reference}")
            vat_raw = str(line_spec.get("vat_treatment") or "included")
            db.add(
                FeeScaleLine(
                    id=uuid.uuid4(),
                    category_id=cat.id,
                    name=str(line_spec.get("name") or "Line").strip()[:300],
                    line_kind=line_kind,
                    amount_kind=amount_kind,
                    default_amount_pence=(
                        int(line_spec["default_amount_pence"])
                        if line_spec.get("default_amount_pence") is not None
                        else None
                    ),
                    band_set_id=band_set_id,
                    vat_treatment=FeeScaleVatTreatment(vat_raw),
                    sort_order=int(line_spec.get("sort_order") if line_spec.get("sort_order") is not None else j),
                    created_at=now,
                    updated_at=now,
                )
            )
    db.flush()


def sync_fee_scales_from_seed(db: Session, *, seed_dir: Path | None = None) -> int:
    """Import missing fee scales from seed. Returns count created (or repaired)."""
    directory = Path(seed_dir) if seed_dir is not None else _seed_dir_from_env()
    if directory is None:
        return 0
    raw = _load_manifest(directory)
    if raw is None:
        return 0

    owner = _first_admin(db)
    if owner is None:
        log.warning("No admin user — cannot apply fee scales seed.")
        return 0

    repair = os.getenv("FEE_SCALES_SEED_REPAIR", "").strip().lower() in ("1", "true", "yes")
    created = 0
    repaired = 0
    try:
        for spec in raw.get("scales") or []:
            ref = (spec.get("reference") or "").strip()
            if not ref:
                continue
            existing = db.execute(select(FeeScale).where(FeeScale.reference == ref)).scalar_one_or_none()
            head_id, sub_id = _resolve_scope(db, spec.get("scope"))
            now = datetime.now(timezone.utc)
            if existing:
                if not repair:
                    continue
                existing.name = str(spec.get("name") or existing.name).strip()[:300]
                existing.vat_rate_bps = int(spec.get("vat_rate_bps") if spec.get("vat_rate_bps") is not None else existing.vat_rate_bps)
                existing.matter_head_type_id = head_id
                existing.matter_sub_type_id = sub_id
                existing.updated_at = now
                _clear_scale_children(db, existing.id)
                _apply_scale_body(db, existing, spec)
                repaired += 1
                continue

            scale = FeeScale(
                id=uuid.uuid4(),
                name=str(spec.get("name") or ref).strip()[:300],
                reference=ref[:200],
                vat_rate_bps=int(spec.get("vat_rate_bps") if spec.get("vat_rate_bps") is not None else 2000),
                matter_head_type_id=head_id,
                matter_sub_type_id=sub_id,
                owner_id=owner.id,
                created_at=now,
                updated_at=now,
            )
            db.add(scale)
            db.flush()
            _apply_scale_body(db, scale, spec)
            created += 1

        if created or repaired:
            db.commit()
            log.info(
                "Fee scales seed from %s: created %s, repaired %s.",
                directory / "manifest.json",
                created,
                repaired,
            )
    except Exception:
        db.rollback()
        raise
    return created + repaired
