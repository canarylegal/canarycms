"""Read-only historical financial validation. JSON to stdout; never changes data.

Exit 0: no issues; 1: inconsistencies; 2: evidence gaps requiring review.
Unexpected execution failures exit 3, without a misleading partial report.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import SessionLocal, begin_report_snapshot
from app.financial_validation import validate_financial_data


def main():
    try:
        with SessionLocal() as db:
            if db.get_bind().dialect.name!='postgresql':
                raise RuntimeError('Operator diagnostics require a PostgreSQL read-only snapshot')
            begin_report_snapshot(db)
            report=validate_financial_data(db)
            db.rollback()
    except Exception as exc:
        print(json.dumps({'status':'execution_failed','error_type':type(exc).__name__}),file=sys.stderr)
        return 3
    print(json.dumps(report,sort_keys=True))
    return {'clear':0,'errors':1,'review_required':2}[report['status']]


if __name__=='__main__':
    raise SystemExit(main())
