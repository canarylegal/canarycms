"""Read-only snapshot audit of existing invoice allocations. Never repairs financial data."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, text
from app.db import SessionLocal
from app.models import CaseInvoice
from app.invoice_allocation_integrity import invoice_consistency


def main():
    findings = []
    checked = 0
    # One stable, read-only snapshot: concurrent corrections cannot manufacture discrepancies.
    with SessionLocal() as db:
        # The pool checkout hook issues SET search_path and already opens a DBAPI
        # transaction. SET TRANSACTION changes it before the first data query,
        # without toggling psycopg autocommit on an in-progress transaction.
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        for invoice in db.scalars(select(CaseInvoice).order_by(CaseInvoice.id).execution_options(yield_per=100)):
            checked += 1
            report = invoice_consistency(db, invoice)
            if not report['consistent']: findings.append(report)
        db.rollback()
    print(json.dumps({'checked_invoices': checked, 'consistent': not findings, 'findings': findings}, default=str))
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
