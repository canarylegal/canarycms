"""On-demand Canary Sign mail operations. Diagnostics never send; no scheduled jobs."""

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import SessionLocal, begin_report_snapshot
from app.models import NotificationOutbox
from app.canary_sign_delivery import KINDS, deliver, diagnostics
from app.notification_outbox import _admin, review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    diagnostic = sub.add_parser("diagnostics")
    diagnostic.add_argument("--request-id", type=uuid.UUID)
    diagnostic.add_argument("--limit", type=int, default=200)
    for action in ("dispatch", "retry", "cancel", "mark-uncertain"):
        p = sub.add_parser(action)
        p.add_argument("--id", type=uuid.UUID, required=True)
        p.add_argument("--actor-id", type=uuid.UUID, required=True)
        if action != "dispatch":
            p.add_argument("--expected-version", type=int, required=True)
            p.add_argument("--reason", required=True)
            p.add_argument("--acknowledge-uncertain", action="store_true")
    args = parser.parse_args()
    try:
        with SessionLocal() as db:
            if args.command == "diagnostics":
                begin_report_snapshot(db)
                result = diagnostics(db, request_id=args.request_id, limit=args.limit)
            else:
                _admin(db, args.actor_id)
                row = db.get(NotificationOutbox, args.id)
                if not row or row.kind not in KINDS:
                    raise ValueError("Not a Canary Sign recipient delivery")
                if args.command != "dispatch":
                    result = review(
                        db,
                        args.id,
                        actor_id=args.actor_id,
                        expected_version=args.expected_version,
                        action=args.command,
                        reason=args.reason,
                        acknowledge_uncertain=args.acknowledge_uncertain,
                    )
                    db.commit()
        if args.command == "dispatch":
            result = deliver(args.id, actor_id=args.actor_id)
        print(json.dumps(result, sort_keys=True))
        return 2 if result.get("state") in ("failed", "uncertain", "sending") else 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "code": getattr(exc, "status_code", None),
                }
            ),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
