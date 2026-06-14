"""Load bundled universal precedent .docx bytes by reserved reference."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.docx_util import validate_docx_package_bytes
from app.file_storage import FILES_ROOT
from app.models import File as DbFile
from app.models import Precedent


def load_global_precedent_docx_bytes(db: Session, reference: str) -> bytes | None:
    """Return on-disk .docx for a global precedent row, or ``None`` if missing/unreadable."""
    ref = (reference or "").strip()
    if not ref:
        return None
    prec = db.execute(
        select(Precedent).where(
            Precedent.reference == ref,
            Precedent.matter_head_type_id.is_(None),
            Precedent.matter_sub_type_id.is_(None),
            Precedent.category_id.is_(None),
        )
    ).scalar_one_or_none()
    if prec is None:
        return None
    frow = db.get(DbFile, prec.file_id)
    if frow is None or not frow.storage_path:
        return None
    path = (FILES_ROOT / frow.storage_path).resolve()
    if not str(path).startswith(str(FILES_ROOT)) or not path.is_file():
        return None
    raw = path.read_bytes()
    try:
        validate_docx_package_bytes(raw)
    except ValueError:
        return None
    return raw
