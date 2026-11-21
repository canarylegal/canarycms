"""Real MVCC reporting snapshots: concurrent corrections cannot mix report sections."""
from datetime import date
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from app.db import SessionLocal, begin_report_snapshot
from app.models import CaseInvoice, CaseInvoiceAllocation
from app.reports_service import report_aged_debt
from tests.test_financial_reports import history, dt


def test_report_snapshot_survives_concurrent_allocation_and_rejects_writes(db):
    if db.bind.dialect.name != 'postgresql': pytest.skip('requires isolated PostgreSQL')
    _, user, case, inv = history(db)
    uid,iid = user.id,inv.id
    with SessionLocal() as reader:
        begin_report_snapshot(reader)
        before=report_aged_debt([uid],reader,as_of=date(2026,1,8))
        assert sum(before[1].values()) == 10000
        with SessionLocal() as writer:
            invoice=writer.get(CaseInvoice,iid)
            invoice.status='approved'; invoice.voided_at=None; invoice.paid_at=dt(8)
            invoice.amount_allocated_pence=10000
            pair=writer.scalar(select(CaseInvoiceAllocation.ledger_pair_id).where(CaseInvoiceAllocation.invoice_id==iid))
            writer.add(CaseInvoiceAllocation(invoice_id=iid,ledger_pair_id=pair,amount_pence=10000,
                allocated_by_user_id=uid,allocated_at=dt(8)))
            writer.commit()
        # Same HTTP/report transaction, including a subsequent export section.
        assert report_aged_debt([uid],reader,as_of=date(2026,1,8)) == before
        assert reader.scalar(text('SHOW transaction_read_only')) == 'on'
        with pytest.raises(DBAPIError): reader.execute(text('UPDATE case_invoice SET total_pence=total_pence WHERE id=:id'),{'id':iid})
        reader.rollback()
    with SessionLocal() as fresh:
        begin_report_snapshot(fresh)
        assert sum(report_aged_debt([uid],fresh,as_of=date(2026,1,8))[1].values()) == 0
