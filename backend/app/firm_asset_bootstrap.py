"""Optional firm branding assets from ``FIRM_ASSETS_SEED_DIR``.

Looks under the env directory (typically the firm package ``assets/`` tree)::

    letterheads/*.docx
    quote-letterheads/*.docx
    logos/*.{png,jpg,jpeg,webp}
    portal-background/*.{png,jpg,jpeg,webp}

On startup, seeds each asset into Admin firm settings storage when that slot is
empty. Existing Admin uploads are never replaced.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_access import user_effective_admin
from app.file_storage import (
    ensure_files_root,
    firm_letterhead_file_paths,
    firm_portal_background_file_paths,
    firm_portal_logo_file_paths,
    firm_quote_letterhead_file_paths,
)
from app.models import File as DbFile
from app.models import FileCategory, FirmSettings, LetterheadStyle, User

log = logging.getLogger(__name__)

_DOCX_SUFFIXES = {".docx"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _seed_dir_from_env() -> Path | None:
    raw = (os.getenv("FIRM_ASSETS_SEED_DIR") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def _first_admin(db: Session) -> User | None:
    for row in db.execute(select(User).order_by(User.created_at.asc())).scalars().all():
        if user_effective_admin(row, db):
            return row
    return None


def _settings_row(db: Session) -> FirmSettings:
    row = db.get(FirmSettings, 1)
    if row is None:
        row = FirmSettings(id=1)
        db.add(row)
        db.flush()
    return row


def _pick_file(directory: Path, *, suffixes: set[str], preferred_stems: tuple[str, ...] = ()) -> Path | None:
    if not directory.is_dir():
        return None
    candidates = sorted(
        (
            p
            for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in suffixes and not p.name.startswith(".")
        ),
        key=lambda p: p.name.lower(),
    )
    if not candidates:
        return None
    for stem in preferred_stems:
        for p in candidates:
            if p.stem.lower() == stem.lower():
                return p
    return candidates[0]


def _store_file(
    db: Session,
    *,
    owner: User,
    source: Path,
    category: FileCategory,
    paths_factory,
    mime_fallback: str,
) -> uuid.UUID:
    ensure_files_root()
    file_id = uuid.uuid4()
    original = source.name
    paths = paths_factory(file_id=file_id, original_filename=original)
    shutil.copy2(source, paths.abs_path)
    size = paths.abs_path.stat().st_size
    mime = mimetypes.guess_type(original)[0] or mime_fallback
    mime = mime.split(";", 1)[0].strip().lower()
    now = datetime.now(timezone.utc)
    frow = DbFile(
        id=file_id,
        case_id=None,
        owner_id=owner.id,
        category=category,
        storage_path=paths.rel_path,
        folder_path="",
        parent_file_id=None,
        is_pinned=False,
        original_filename=Path(original).name,
        mime_type=mime,
        size_bytes=size,
        version=1,
        checksum=None,
        created_at=now,
        updated_at=now,
    )
    db.add(frow)
    db.flush()
    return file_id


def sync_firm_assets_from_seed(db: Session) -> int:
    """Seed missing firm branding slots from package assets. Returns count seeded."""
    seed_dir = _seed_dir_from_env()
    if seed_dir is None:
        log.info("FIRM_ASSETS_SEED_DIR unset or missing — skipping firm asset seed.")
        return 0

    owner = _first_admin(db)
    if owner is None:
        log.warning("Firm asset seed skipped: no admin user to own seeded files.")
        return 0

    row = _settings_row(db)
    seeded = 0
    now = datetime.now(timezone.utc)

    if not row.letterhead_file_id:
        src = _pick_file(
            seed_dir / "letterheads",
            suffixes=_DOCX_SUFFIXES,
            preferred_stems=("letterhead", "firm_letterhead"),
        )
        if src is not None:
            fid = _store_file(
                db,
                owner=owner,
                source=src,
                category=FileCategory.firm_letterhead,
                paths_factory=firm_letterhead_file_paths,
                mime_fallback="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            row.letterhead_file_id = fid
            row.letterhead_style = LetterheadStyle.digital
            seeded += 1
            log.info("Seeded firm letterhead from %s", src)

    if not row.quote_letterhead_file_id:
        src = _pick_file(
            seed_dir / "quote-letterheads",
            suffixes=_DOCX_SUFFIXES,
            preferred_stems=("quote_letterhead", "quote-letterhead", "letterhead"),
        )
        if src is not None:
            fid = _store_file(
                db,
                owner=owner,
                source=src,
                category=FileCategory.firm_letterhead,
                paths_factory=firm_quote_letterhead_file_paths,
                mime_fallback="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            row.quote_letterhead_file_id = fid
            row.quote_letterhead_style = LetterheadStyle.digital
            seeded += 1
            log.info("Seeded quote letterhead from %s", src)

    if not row.portal_logo_file_id:
        src = _pick_file(
            seed_dir / "logos",
            suffixes=_IMAGE_SUFFIXES,
            preferred_stems=("logo", "portal_logo", "portal-logo"),
        )
        if src is not None:
            fid = _store_file(
                db,
                owner=owner,
                source=src,
                category=FileCategory.firm_portal_logo,
                paths_factory=firm_portal_logo_file_paths,
                mime_fallback="image/png",
            )
            row.portal_logo_file_id = fid
            seeded += 1
            log.info("Seeded portal logo from %s", src)

    if not row.portal_background_file_id:
        src = _pick_file(
            seed_dir / "portal-background",
            suffixes=_IMAGE_SUFFIXES,
            preferred_stems=("background", "portal_background", "portal-background"),
        )
        if src is not None:
            fid = _store_file(
                db,
                owner=owner,
                source=src,
                category=FileCategory.firm_portal_background,
                paths_factory=firm_portal_background_file_paths,
                mime_fallback="image/jpeg",
            )
            row.portal_background_file_id = fid
            seeded += 1
            log.info("Seeded portal background from %s", src)

    if seeded:
        row.updated_at = now
        db.add(row)
        db.commit()
    return seeded
