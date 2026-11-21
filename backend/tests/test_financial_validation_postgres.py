"""Diagnostics use real read-only MVCC snapshots and do not observe half a correction."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.db import SessionLocal,begin_report_snapshot
from app.financial_validation import validate_financial_data
from app.models import CaseInvoice
from tests.test_financial_validation import fixture


def test_diagnostics_snapshot_is_stable_and_database_enforces_no_writes(db):
    if db.bind.dialect.name!='postgresql':pytest.skip('isolated PostgreSQL required')
    _,_,_,invoice,_=fixture(db)
    iid=invoice.id
    with SessionLocal() as reader:
        begin_report_snapshot(reader)
        before=validate_financial_data(reader)
        with SessionLocal() as writer:
            inv=writer.get(CaseInvoice,iid);inv.amount_allocated_pence=123;writer.commit()
        assert validate_financial_data(reader)==before
        with pytest.raises(DBAPIError):reader.execute(text('UPDATE case_invoice SET amount_allocated_pence=0 WHERE id=:id'),{'id':iid})
        reader.rollback()
    with SessionLocal() as reader:
        begin_report_snapshot(reader)
        assert any(f['id']==str(iid) and f['code']=='allocation_cached_total_mismatch' for f in validate_financial_data(reader)['findings'])
    # This corruption is test-only; keep the shared isolated workflow fixture consistent.
    with SessionLocal() as writer:
        writer.get(CaseInvoice,iid).amount_allocated_pence=0;writer.commit()
