"""Operator-only preview and explicitly reviewed firm-wide period reopening."""
import argparse
import json
from pathlib import Path
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from app.db import SessionLocal, begin_report_snapshot
from app.period_reopening import preview_reopening, reopen_period


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    preview = sub.add_parser('preview')
    preview.add_argument('--reconciliation-id', required=True, type=uuid.UUID)
    apply = sub.add_parser('reopen')
    apply.add_argument('--reconciliation-id', required=True, type=uuid.UUID)
    apply.add_argument('--actor-id', required=True, type=uuid.UUID)
    apply.add_argument('--reviewed-hash', required=True)
    apply.add_argument('--reason', required=True)
    args = parser.parse_args(argv)
    try:
        with SessionLocal() as db:
            if db.get_bind().dialect.name != 'postgresql':
                raise RuntimeError('PostgreSQL required')
            if args.command == 'preview':
                begin_report_snapshot(db)
                result = preview_reopening(db, args.reconciliation_id)
                db.rollback()
            else:
                result = reopen_period(db, reconciliation_id=args.reconciliation_id, actor_id=args.actor_id,
                                       expected_hash=args.reviewed_hash, reason=args.reason)
                db.commit()
    except Exception as exc:
        error = dict(status='failed', error_type=type(exc).__name__)
        if isinstance(exc, HTTPException):
            error.update(code=exc.status_code, detail=exc.detail)
        print(json.dumps(error), file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
