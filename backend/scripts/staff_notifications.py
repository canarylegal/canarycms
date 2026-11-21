"""On-demand staff outbox operations. No scheduler, automatic retry or login-code processing."""

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db import SessionLocal, begin_report_snapshot
from app.models import NotificationOutbox, NotificationAttempt
from app.notification_outbox import deliver, review, summary, _admin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    listing = subs.add_parser("list")
    listing.add_argument(
        "--state",
        choices=["pending", "sending", "sent", "failed", "uncertain", "cancelled"],
    )
    listing.add_argument("--limit", type=int, default=100)
    inspect = subs.add_parser("inspect")
    inspect.add_argument("--id", type=uuid.UUID, required=True)
    dispatch = subs.add_parser("dispatch")
    dispatch.add_argument("--id", type=uuid.UUID, required=True)
    dispatch.add_argument("--actor-id", type=uuid.UUID, required=True)
    batch = subs.add_parser("dispatch-pending")
    batch.add_argument("--limit", type=int, default=25)
    batch.add_argument("--actor-id", type=uuid.UUID, required=True)
    for action in ("retry", "cancel", "mark-uncertain"):
        cmd = subs.add_parser(action)
        cmd.add_argument("--id", type=uuid.UUID, required=True)
        cmd.add_argument("--actor-id", type=uuid.UUID, required=True)
        cmd.add_argument("--expected-version", type=int, required=True)
        cmd.add_argument("--reason", required=True)
        cmd.add_argument("--acknowledge-uncertain", action="store_true")
    args = parser.parse_args()
    try:
        if hasattr(args, "limit") and not 1 <= args.limit <= 200:
            raise ValueError("Limit must be between 1 and 200")
        if args.command == "dispatch":
            result = deliver(args.id, actor_id=args.actor_id)
        elif args.command == "dispatch-pending":
            with SessionLocal() as db:
                _admin(db, args.actor_id)
                ids = list(
                    db.scalars(
                        select(NotificationOutbox.id)
                        .where(NotificationOutbox.state == "pending")
                        .order_by(NotificationOutbox.created_at, NotificationOutbox.id)
                        .limit(args.limit)
                    )
                )
            result = [deliver(identity, actor_id=args.actor_id) for identity in ids]
        else:
            with SessionLocal() as db:
                if args.command in ("list", "inspect"):
                    begin_report_snapshot(db)
                if args.command == "list":
                    query = (
                        select(NotificationOutbox)
                        .order_by(NotificationOutbox.created_at, NotificationOutbox.id)
                        .limit(args.limit)
                    )
                    if args.state:
                        query = query.where(NotificationOutbox.state == args.state)
                    result = [summary(row) for row in db.scalars(query)]
                    db.rollback()
                elif args.command == "inspect":
                    row = db.get(NotificationOutbox, args.id)
                    if row is None:
                        raise ValueError("Unknown notification")
                    result = summary(row)
                    result["attempts"] = [
                        {
                            "id": str(a.id),
                            "state": a.state,
                            "code": a.code,
                            "transport": a.transport,
                            "started_at": str(a.started_at),
                            "finished_at": str(a.finished_at),
                            "operator_id": str(a.operator_id),
                        }
                        for a in db.scalars(
                            select(NotificationAttempt)
                            .where(NotificationAttempt.notification_id == row.id)
                            .order_by(
                                NotificationAttempt.started_at, NotificationAttempt.id
                            )
                        )
                    ]
                    db.rollback()
                else:
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
        print(json.dumps(result, sort_keys=True))
        results = result if isinstance(result, list) else [result]
        return (
            2
            if any(
                r.get("state") in ("failed", "uncertain", "sending") for r in results
            )
            else 0
        )
    except Exception as exc:
        # Do not expose provider responses, recipients, bodies, tokens or credentials.
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
