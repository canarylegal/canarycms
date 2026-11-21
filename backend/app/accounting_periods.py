"""UTC accounting cutoffs. Shared writer locks exclude firm-wide period transitions."""
from datetime import timezone
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models import ClientAccountReconciliation, ReconciliationStatus


def lock_periods(db, *, exclusive=False):
    if db.get_bind().dialect.name == 'postgresql':
        function = 'pg_try_advisory_xact_lock' if exclusive else 'pg_try_advisory_xact_lock_shared'
        if not db.scalar(text(f'SELECT {function}(582013724, 1)')):
            raise HTTPException(409, 'Accounting periods are being reviewed. Retry after the current operation completes.')


def require_accounting_open(db, at):
    lock_periods(db)
    day = (at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)).date()
    closed = db.scalar(select(ClientAccountReconciliation.id).where(
        ClientAccountReconciliation.status == ReconciliationStatus.approved,
        ClientAccountReconciliation.period_end_date >= day).limit(1))
    if closed:
        raise HTTPException(409, 'This accounting period is approved. Reopen the firm-wide reconciliation with a reason before changing it.')


def period_impact(db, period_end_date, *, bank_id=None):
    """Review scope and still-approved barriers; no automatic cascade or reapproval."""
    from app.models import BankReconciliation
    firm = list(db.scalars(select(ClientAccountReconciliation.id).where(
        ClientAccountReconciliation.status == ReconciliationStatus.approved).order_by(ClientAccountReconciliation.id)))
    query = select(BankReconciliation.id).where(BankReconciliation.status == 'approved')
    if bank_id is not None:
        query = query.where(BankReconciliation.firm_bank_account_id == bank_id)
    banks = list(db.scalars(query.order_by(BankReconciliation.id)))
    return dict(period_end_date=period_end_date.isoformat(), bank_id=str(bank_id) if bank_id else None,
        reports_requiring_review=['bank_reconciliation'] if bank_id else
            ['client_office_balances', 'ledger_activity', 'billing', 'aged_debt', 'accountant_exports', 'reconciliations'],
        remaining_firm_approvals=list(map(str, firm)), remaining_bank_approvals=list(map(str, banks)),
        reapproval_required=True)
