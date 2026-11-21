"""Operator review CLI. Default review is read-only; applying requires explicit flags."""
import argparse
import json
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from app.db import SessionLocal, begin_report_snapshot
from app.historical_corrections import investigate_history, preview_unmatch, apply_unmatch


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('investigate')
    preview = commands.add_parser('preview-unmatch')
    preview.add_argument('--line-id', type=uuid.UUID, required=True)
    apply = commands.add_parser('apply-unmatch')
    apply.add_argument('--plan', type=Path, required=True)
    apply.add_argument('--actor-id', type=uuid.UUID, required=True)
    apply.add_argument('--reason', required=True)
    apply.add_argument('--approve-plan-hash', required=True)
    args = parser.parse_args(argv)
    try:
        with SessionLocal() as db:
            if db.get_bind().dialect.name != 'postgresql':
                raise RuntimeError('PostgreSQL required')
            if args.command == 'apply-unmatch':
                report = apply_unmatch(db, plan=json.loads(args.plan.read_text()), actor_id=args.actor_id,
                                      reason=args.reason, approved_hash=args.approve_plan_hash)
                db.commit()  # Never print success before the durable commit.
            else:
                begin_report_snapshot(db)
                report = investigate_history(db) if args.command == 'investigate' else preview_unmatch(db, args.line_id)
                db.rollback()
    except Exception as exc:
        error = dict(status='failed', error_type=type(exc).__name__)
        if isinstance(exc, HTTPException):
            error.update(detail=exc.detail, code=exc.status_code)
        print(json.dumps(error), file=sys.stderr)
        return 3
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
