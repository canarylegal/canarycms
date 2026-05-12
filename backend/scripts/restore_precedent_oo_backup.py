#!/usr/bin/env python3
"""Restore a precedent ``.docx`` from the OnlyOffice pre-edit backup (``*.oo_backup``), if present.

Opening a precedent in ONLYOFFICE creates ``<storage_path>.oo_backup`` once. After **Save**, the callback
removes that backup — so restore only works if you have not saved, or an old backup still exists.

Examples::

    docker compose exec backend python scripts/restore_precedent_oo_backup.py --reference BLANK_LETTER
    docker compose exec backend python scripts/restore_precedent_oo_backup.py --precedent-id <uuid>
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os

from sqlalchemy import select

from app.db import SessionLocal
from app.file_storage import FILES_ROOT
from app.models import File as DbFile
from app.models import Precedent
from app.precedent_constants import BLANK_LETTER_PRECEDENT_REFERENCE


def main() -> None:
    ap = argparse.ArgumentParser(description="Restore precedent file from .oo_backup")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--reference", help="Precedent.reference (e.g. BLANK_LETTER)")
    g.add_argument("--precedent-id", help="Precedent UUID")
    args = ap.parse_args()

    os.environ.setdefault("FILES_ROOT", "/data/files")

    db = SessionLocal()
    try:
        if args.precedent_id:
            import uuid as uuid_mod

            p = db.get(Precedent, uuid_mod.UUID(args.precedent_id.strip()))
        else:
            ref = (args.reference or "").strip()
            p = db.execute(select(Precedent).where(Precedent.reference == ref)).scalar_one_or_none()
        if p is None:
            print("Precedent not found.", file=sys.stderr)
            sys.exit(1)
        f = db.get(DbFile, p.file_id)
        if f is None:
            print("Precedent file row missing.", file=sys.stderr)
            sys.exit(1)
        src = (FILES_ROOT / f.storage_path).resolve()
        backup = Path(str(src) + ".oo_backup")
        if not backup.is_file():
            print(f"No backup at {backup}", file=sys.stderr)
            sys.exit(1)
        shutil.copy2(backup, src)
        sz = src.stat().st_size
        f.size_bytes = sz
        db.commit()
        print(f"OK: restored {src} from backup ({sz} bytes)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
