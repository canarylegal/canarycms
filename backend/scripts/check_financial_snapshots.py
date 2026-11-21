"""Read-only verification of every retained approval archive; no repairs or backfill."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db import SessionLocal, begin_report_snapshot
from app.models import (
    FinancialReportSnapshot,
    ClientAccountReconciliation,
    BankReconciliation,
)
from app.financial_report_snapshots import verify_chain
from app.financial_snapshot_capture import encode


def main():
    try:
        with SessionLocal() as db:
            if db.get_bind().dialect.name != "postgresql":
                raise RuntimeError("PostgreSQL required")
            begin_report_snapshot(db)
            snapshots = list(
                db.scalars(
                    select(FinancialReportSnapshot).order_by(FinancialReportSnapshot.id)
                )
            )
            for row in snapshots:
                verify_chain(db, row)
            sources = {}
            for snapshot in snapshots:
                key = (snapshot.source_kind, snapshot.source_id)
                if key not in sources or sources[key].version < snapshot.version:
                    sources[key] = snapshot
            legacy = []
            for kind, model in [
                ("firm", ClientAccountReconciliation),
                ("bank", BankReconciliation),
            ]:
                for row in db.scalars(
                    select(model).where(model.status == "approved").order_by(model.id)
                ):
                    if (kind, row.id) not in sources:
                        legacy.append(dict(source_kind=kind, source_id=str(row.id)))
                    elif encode(sources[kind, row.id].approved_at) != encode(
                        row.approved_at
                    ):
                        raise RuntimeError(
                            "Current approval does not match its archive"
                        )
            result = dict(
                status="verified",
                snapshots=len(snapshots),
                legacy_unarchived=legacy,
                archive_hashes={str(row.id): row.archive_sha256 for row in snapshots},
            )
            db.rollback()
    except Exception as exc:
        print(
            json.dumps({"status": "failed", "error_type": type(exc).__name__}),
            file=sys.stderr,
        )
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
