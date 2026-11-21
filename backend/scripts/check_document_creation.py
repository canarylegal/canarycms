"""Read-only inventory of generated candidates; never delete or publish orphan bytes."""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db import SessionLocal, begin_report_snapshot
from app.models import File
from app.file_storage import FILES_ROOT
from app.document_durability import safe_path


def main():
    try:
        with SessionLocal() as db:
            begin_report_snapshot(db)
            rows = list(
                db.scalars(
                    select(File).where(File.storage_path.startswith(".created/"))
                )
            )
            referenced = {row.storage_path for row in rows}
            failures = []
            for row in rows:
                path = safe_path(FILES_ROOT, row.storage_path)
                if not path.is_file():
                    failures.append({"file_id": str(row.id), "code": "missing"})
                else:
                    with path.open("rb") as f:
                        checksum = hashlib.file_digest(f, "sha256").hexdigest()
                    if checksum != row.checksum:
                        failures.append({"file_id": str(row.id), "code": "checksum"})
            candidates = sorted(
                str(p.relative_to(FILES_ROOT))
                for p in (FILES_ROOT / ".created").rglob("*")
                if p.is_file() and str(p.relative_to(FILES_ROOT)) not in referenced
            )
            print(
                json.dumps(
                    {
                        "checked": len(rows),
                        "failures": failures,
                        "unreferenced_candidates": candidates,
                        "note": "Candidates may belong to in-flight transactions. Retain for review; retry using the original operation ID.",
                    },
                    sort_keys=True,
                )
            )
            db.rollback()
            return 2 if failures else 0
    except Exception as exc:
        print(
            json.dumps({"status": "failed", "error_type": type(exc).__name__}),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
