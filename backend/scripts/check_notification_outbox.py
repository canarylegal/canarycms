"""Read-only outbox integrity inventory for restart/restore checks; never sends mail."""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db import SessionLocal, begin_report_snapshot
from app.models import NotificationOutbox, NotificationAttempt
from app.notification_outbox import summary, _message


def main():
    with SessionLocal() as db:
        begin_report_snapshot(db)
        rows = []
        for row in db.scalars(
            select(NotificationOutbox).order_by(NotificationOutbox.id)
        ):
            _message(row)  # Authenticate encryption and verify the frozen payload hash.
            item = summary(row)
            item["payload_sha256"] = row.payload_sha256
            item["attempts"] = [
                {"id": str(a.id), "state": a.state, "code": a.code}
                for a in db.scalars(
                    select(NotificationAttempt)
                    .where(NotificationAttempt.notification_id == row.id)
                    .order_by(NotificationAttempt.id)
                )
            ]
            rows.append(item)
        print(
            json.dumps(
                {
                    "count": len(rows),
                    "states": sorted({r["state"] for r in rows}),
                    "sha256": hashlib.sha256(
                        json.dumps(rows, sort_keys=True).encode()
                    ).hexdigest(),
                },
                sort_keys=True,
            )
        )
        db.rollback()


if __name__ == "__main__":
    main()
