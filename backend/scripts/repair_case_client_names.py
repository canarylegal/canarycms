#!/usr/bin/env python3
"""Recompute Case.client_name from matter contacts (type client). Safe to re-run."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

from sqlalchemy import select

from app.case_client_sync import sync_case_client_name
from app.db import SessionLocal
from app.models import Case


def main() -> None:
    db = SessionLocal()
    try:
        case_ids = list(db.execute(select(Case.id)).scalars().all())
        n = 0
        for cid in case_ids:
            sync_case_client_name(db, cid)
            n += 1
        db.commit()
        print(f"Synced client_name for {n} matter(s).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
