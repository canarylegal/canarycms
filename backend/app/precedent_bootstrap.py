"""Optional bundled precedent templates (Docker image / fresh deploy).

Looks for ``manifest.json`` under ``PRECEDENTS_SEED_DIR`` (default ``/app/precedents_seed``).
When the ``precedent`` table is empty, imports categories, files, and precedent rows so new
environments match matter sub-types by name (see manifest format from ``export_precedent_seed``).

Entries with ``"global": true`` become firm-wide precedents (no matter head/sub/category), e.g.
the reserved blank letter template (``reference``: ``BLANK_LETTER``).

On every startup, :func:`sync_missing_global_precedents_from_seed` adds any bundled global
precedent whose ``reference`` is not yet in the database (admin edits to existing rows are kept).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.file_storage import ensure_files_root, precedent_file_paths
from app.precedent_constants import (
    BLANK_LETTER_PRECEDENT_REFERENCE,
    COMPLETION_STATEMENT_PRECEDENT_REFERENCE,
    INVOICE_TEMPLATE_PRECEDENT_REFERENCE,
    QUOTE_EMAIL_PRECEDENT_REFERENCE,
    QUOTE_TEMPLATE_PRECEDENT_REFERENCE,
)
from app.models import (
    File as DbFile,
    FileCategory,
    MatterHeadType,
    MatterSubType,
    Precedent,
    PrecedentCategory,
    PrecedentKind,
    User,
    UserRole,
)

log = logging.getLogger(__name__)

DEFAULT_SEED_DIR = Path(os.getenv("PRECEDENTS_SEED_DIR", str(Path(__file__).parent.parent / "precedents_seed")))


def _resolve_sub_type_id(
    db: Session,
    *,
    matter_head_type_name: str,
    matter_sub_type_name: str,
) -> uuid.UUID | None:
    head = db.execute(
        select(MatterHeadType).where(MatterHeadType.name == matter_head_type_name)
    ).scalar_one_or_none()
    if not head:
        return None
    sub = db.execute(
        select(MatterSubType).where(
            MatterSubType.head_type_id == head.id,
            MatterSubType.name == matter_sub_type_name,
        )
    ).scalar_one_or_none()
    return sub.id if sub else None


def _first_admin_id(db: Session) -> uuid.UUID | None:
    row = db.execute(select(User).where(User.role == UserRole.admin)).scalars().first()
    return row.id if row else None


def _load_seed_manifest() -> dict[str, Any] | None:
    manifest_path = DEFAULT_SEED_DIR / "manifest.json"
    if not manifest_path.is_file():
        log.info("No precedent seed manifest at %s — skipping.", manifest_path)
        return None
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        log.warning("Unsupported precedent seed version: %s", raw.get("version"))
        return None
    return raw


def _precedent_reference_exists(db: Session, reference: str) -> bool:
    ref = (reference or "").strip()
    if not ref:
        return False
    return (
        db.execute(
            select(Precedent.id).where(func.lower(Precedent.reference) == ref.casefold()).limit(1)
        ).first()
        is not None
    )


def _validate_seed_precedent_kind(reference: str, kind: PrecedentKind) -> bool:
    if reference == BLANK_LETTER_PRECEDENT_REFERENCE:
        if kind != PrecedentKind.letter:
            log.warning("Precedent seed: %s must be kind=letter — got %s", reference, kind)
            return False
    elif reference in (
        INVOICE_TEMPLATE_PRECEDENT_REFERENCE,
        COMPLETION_STATEMENT_PRECEDENT_REFERENCE,
        QUOTE_TEMPLATE_PRECEDENT_REFERENCE,
    ):
        if kind != PrecedentKind.document:
            log.warning("Precedent seed: %s must be kind=document — got %s", reference, kind)
            return False
    elif reference == QUOTE_EMAIL_PRECEDENT_REFERENCE:
        if kind != PrecedentKind.email:
            log.warning("Precedent seed: %s must be kind=email — got %s", reference, kind)
            return False
    return True


def _import_precedent_from_seed(
    db: Session,
    *,
    admin_id: uuid.UUID,
    payload: dict[str, Any],
    cat_key_to_id: dict[tuple[str, str, str], uuid.UUID],
) -> bool:
    fname = (payload.get("bundle_file") or "").strip()
    if not fname:
        return False
    src = DEFAULT_SEED_DIR / fname
    if not src.is_file():
        log.warning("Precedent seed: missing file %s — skip %r", fname, payload.get("name"))
        return False

    is_global = bool(payload.get("global"))
    mh_id: uuid.UUID | None = None
    ms_id: uuid.UUID | None = None
    cid: uuid.UUID | None = None

    if is_global:
        pass
    else:
        head_name = (payload.get("matter_head_type_name") or "").strip()
        sub_name = (payload.get("matter_sub_type_name") or "").strip()
        cat_name = (payload.get("category_name") or "").strip()
        cid = cat_key_to_id.get((head_name, sub_name, cat_name))
        if not cid:
            log.warning("Precedent seed: skip precedent %r — category not resolved.", payload.get("name"))
            return False
        pc = db.get(PrecedentCategory, cid)
        ms_id = pc.matter_sub_type_id if pc else None
        sub = db.get(MatterSubType, ms_id) if ms_id else None
        mh_id = sub.head_type_id if sub else None

    kind_s = (payload.get("kind") or "document").strip().lower()
    try:
        kind = PrecedentKind(kind_s)
    except ValueError:
        kind = PrecedentKind.document

    ref = (payload.get("reference") or "SEED").strip()[:200]
    if not _validate_seed_precedent_kind(ref, kind):
        return False

    prec_id = uuid.uuid4()
    file_id = uuid.uuid4()
    original_filename = (payload.get("original_filename") or Path(fname).name).strip() or "precedent.bin"
    mime_type = (payload.get("mime_type") or "application/octet-stream").strip()
    size_bytes = int(payload.get("size_bytes") or src.stat().st_size)

    paths = precedent_file_paths(precedent_id=prec_id, file_id=file_id, original_filename=original_filename)
    shutil.copy2(src, paths.abs_path)

    now = datetime.now(timezone.utc)
    db.add(
        DbFile(
            id=file_id,
            case_id=None,
            owner_id=admin_id,
            category=FileCategory.precedent,
            folder_path="",
            is_pinned=False,
            storage_path=paths.rel_path,
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            version=1,
            checksum=None,
            parent_file_id=None,
            oo_compose_pending=False,
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        Precedent(
            id=prec_id,
            name=(payload.get("name") or original_filename)[:300],
            reference=ref,
            kind=kind,
            file_id=file_id,
            matter_head_type_id=mh_id,
            matter_sub_type_id=ms_id,
            category_id=cid,
            created_at=now,
            updated_at=now,
        )
    )
    return True


def _build_category_map(db: Session, categories_payload: list[dict[str, Any]]) -> dict[tuple[str, str, str], uuid.UUID]:
    cat_key_to_id: dict[tuple[str, str, str], uuid.UUID] = {}
    for c in categories_payload:
        head_name = (c.get("matter_head_type_name") or "").strip()
        sub_name = (c.get("matter_sub_type_name") or "").strip()
        cat_name = (c.get("name") or "").strip()
        if not head_name or not sub_name or not cat_name:
            continue
        sid = _resolve_sub_type_id(db, matter_head_type_name=head_name, matter_sub_type_name=sub_name)
        if not sid:
            log.warning(
                "Precedent seed: unknown matter type %s / %s — skip category %s",
                head_name,
                sub_name,
                cat_name,
            )
            continue
        existing = db.execute(
            select(PrecedentCategory).where(
                PrecedentCategory.matter_sub_type_id == sid,
                PrecedentCategory.name == cat_name,
            )
        ).scalar_one_or_none()
        if existing:
            cid = existing.id
        else:
            cid = uuid.uuid4()
            now_cat = datetime.now(timezone.utc)
            db.add(
                PrecedentCategory(
                    id=cid,
                    matter_sub_type_id=sid,
                    name=cat_name,
                    sort_order=int(c.get("sort_order") or 0),
                    created_at=now_cat,
                    updated_at=now_cat,
                )
            )
        cat_key_to_id[(head_name, sub_name, cat_name)] = cid
    db.flush()
    return cat_key_to_id


def sync_missing_global_precedents_from_seed(db: Session) -> int:
    """Import bundled global precedents missing by reference. Returns count added."""
    raw = _load_seed_manifest()
    if raw is None:
        return 0

    admin_id = _first_admin_id(db)
    if admin_id is None:
        log.warning("No admin user — cannot sync global precedents from seed.")
        return 0

    inserted = 0
    try:
        ensure_files_root()
        for p in raw.get("precedents") or []:
            if not p.get("global"):
                continue
            ref = (p.get("reference") or "").strip()
            if not ref or _precedent_reference_exists(db, ref):
                continue
            if _import_precedent_from_seed(db, admin_id=admin_id, payload=p, cat_key_to_id={}):
                inserted += 1
        if inserted:
            db.commit()
            log.info("Precedent seed: added %s missing global precedent(s).", inserted)
    except Exception:
        db.rollback()
        raise
    return inserted


def apply_precedent_seed_if_empty(db: Session) -> bool:
    """Return True if seed was applied."""

    n = db.execute(select(Precedent.id).limit(1)).first()
    if n is not None:
        return False

    raw = _load_seed_manifest()
    if raw is None:
        return False

    admin_id = _first_admin_id(db)
    if not admin_id:
        log.warning("No admin user — cannot apply precedent seed.")
        return False

    prec_list = raw.get("precedents") or []
    if not prec_list:
        log.info("Precedent seed manifest has no precedents — skipping.")
        return False

    try:
        ensure_files_root()
        cat_key_to_id = _build_category_map(db, raw.get("categories") or [])

        inserted = 0
        for p in prec_list:
            if _import_precedent_from_seed(db, admin_id=admin_id, payload=p, cat_key_to_id=cat_key_to_id):
                inserted += 1

        if len(prec_list) > 0 and inserted == 0:
            db.rollback()
            log.warning(
                "Precedent seed: manifest listed precedents but none could be imported "
                "(check matter type names and bundle files)."
            )
            return False

        db.commit()
    except Exception:
        db.rollback()
        raise
    log.info("Precedent seed applied from %s.", DEFAULT_SEED_DIR / "manifest.json")
    return True
