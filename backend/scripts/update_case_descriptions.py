#!/usr/bin/env python3
"""Set every matter description to [sub-type pre-fix] + random UK address."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

from datetime import datetime, timezone

from sqlalchemy import select

from app.case_matter_description import build_matter_description, random_uk_address_lines
from app.db import SessionLocal
from app.models import Case, MatterSubType


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Case, MatterSubType.prefix).join(
                MatterSubType, Case.matter_sub_type_id == MatterSubType.id
            )
        ).all()
        n = 0
        for case, prefix in rows:
            case.title = build_matter_description(prefix, random_uk_address_lines())[:300]
            case.updated_at = datetime.now(timezone.utc)
            db.add(case)
            n += 1
        # Cases without a sub-type: address only
        orphan = db.execute(
            select(Case).where(Case.matter_sub_type_id.is_(None))
        ).scalars().all()
        for case in orphan:
            case.title = build_matter_description(None, random_uk_address_lines())[:300]
            case.updated_at = datetime.now(timezone.utc)
            db.add(case)
            n += 1
        db.commit()
        print(f"Updated description for {n} matter(s).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
