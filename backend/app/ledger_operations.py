"""Public ledger operations. Posting, request receipt and audit share one commit."""
import json
import uuid

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.audit import log_event
from app.deps import require_case_access
from app.ledger_audit import log_ledger_post
from app.ledger_integrity import lock_matters, record_receipt, request_receipt, require_posting_period
from app.ledger_service import (LedgerPostResult, _balance, _reject_client_deficit,
                                _try_lock_ledger_pair, post_transaction)
from app.models import (BankStatementLine, CaseInvoice, CaseInvoiceAllocation, InterMatterJournal,
                        LedgerAccount, LedgerEntry, LedgerOperation, LedgerDirection)
from app.permission_checks import assert_may_post_anticipated, assert_may_post_ledger
from app.schemas import LedgerPostCreate
from app.timeutil import utcnow


def require_actor(db, user, *case_ids):
    if not user.is_active:
        raise HTTPException(403, 'Active staff account required')
    for case_id in sorted(set(case_ids)):
        require_case_access(case_id, user, db)


def post_ledger_operation(case_id, payload, user, db):
    require_actor(db, user, case_id)
    if payload.anticipated:
        assert_may_post_anticipated(user, db)
    else:
        assert_may_post_ledger(user, payload, db)
    fingerprint, previous = request_receipt(db, user, 'posting', payload, case_id)
    if previous:
        result = json.loads(previous.result_json)
        return LedgerPostResult(uuid.UUID(result['pair_id']), result['is_approved'], result['is_anticipated'])
    result = post_transaction(case_id, payload, user, db)
    log_ledger_post(db, actor_user_id=user.id, case_id=case_id, pair_id=result.pair_id,
                    payload=payload, is_approved=result.is_approved)
    record_receipt(db, user, 'posting', payload, fingerprint, result.pair_id,
        {'pair_id': result.pair_id, 'is_approved': result.is_approved, 'is_anticipated': result.is_anticipated})
    return result


def reversal_legs(db, case_id, pair_id, user, *, journal_id=None):
    """Lock and validate before creating any compensation. Shared with whole-journal reversal."""
    require_actor(db, user, case_id)
    _try_lock_ledger_pair(db, pair_id)
    lock_matters(db, case_id)
    legs = list(db.scalars(select(LedgerEntry).where(LedgerEntry.pair_id == pair_id)
        .order_by(LedgerEntry.id).with_for_update().execution_options(populate_existing=True)))
    if not legs:
        raise HTTPException(404, 'Posting not found')
    accounts = [db.get(LedgerAccount, leg.account_id) for leg in legs]
    require_actor(db, user, *(a.case_id for a in accounts))
    if (any(a.case_id != case_id for a in accounts) or len(legs) not in (1, 2)
            or len({a.account_type for a in accounts}) != len(legs)
            or len({leg.amount_pence for leg in legs}) != 1
            or any(not leg.is_approved or leg.is_anticipated or leg.amount_pence <= 0 for leg in legs)):
        raise HTTPException(409, 'Reversal requires a valid approved posting on this matter')
    directions = {f'{a.account_type.value}_direction': 'debit' if leg.direction == LedgerDirection.credit else 'credit'
                  for a, leg in zip(accounts, legs)}
    assert_may_post_ledger(user, LedgerPostCreate(description='Reversal', amount_pence=legs[0].amount_pence,
                                                **directions), db)
    if db.scalar(select(CaseInvoice.id).where(or_(CaseInvoice.ledger_pair_id == pair_id,
                                                  CaseInvoice.reversal_pair_id == pair_id)).limit(1)):
        raise HTTPException(409, 'Use the invoice correction workflow for invoice postings')
    journal = db.scalar(select(InterMatterJournal.id).where(or_(InterMatterJournal.from_pair_id == pair_id,
                                                               InterMatterJournal.to_pair_id == pair_id)).limit(1))
    if journal and journal != journal_id:
        raise HTTPException(409, 'Reverse the whole inter-matter journal, not an individual leg')
    if db.scalar(select(LedgerOperation.id).where(LedgerOperation.kind == 'reverse_posting', or_(
            LedgerOperation.reverses_id == pair_id, LedgerOperation.result_id == pair_id)).limit(1)):
        raise HTTPException(409, 'This posting was already reversed or is a reversal')
    from app.invoice_allocation_integrity import active_allocation
    if db.scalar(select(CaseInvoiceAllocation.id).where(CaseInvoiceAllocation.ledger_pair_id == pair_id, active_allocation()).limit(1)):
        raise HTTPException(409, 'Correct invoice allocations before reversing this posting')
    if db.scalar(select(BankStatementLine.id).where(BankStatementLine.matched_pair_id == pair_id).limit(1)):
        raise HTTPException(409, 'Unmatch this posting through the bank correction workflow before reversing it')
    require_posting_period(db, {leg.firm_bank_account_id for account, leg in zip(accounts, legs)
                               if account.account_type.value == "client"})
    for account, leg in zip(accounts, legs):
        if account.account_type.value == 'client' and leg.direction == LedgerDirection.credit:
            _reject_client_deficit(_balance(account.id, db) - leg.amount_pence)
            _reject_client_deficit(_balance(account.id, db, bank_id=leg.firm_bank_account_id,
                                            bank_only=True) - leg.amount_pence)
    return legs


def compensate(db, legs, user, reason):
    """Preserve original bank and party, including archived banks; never resolve a new default."""
    pair_id = uuid.uuid4()
    for leg in legs:
        db.add(LedgerEntry(id=uuid.uuid4(), pair_id=pair_id, account_id=leg.account_id,
            direction=LedgerDirection.debit if leg.direction == LedgerDirection.credit else LedgerDirection.credit,
            amount_pence=leg.amount_pence, description=f'Reversal: {reason}'[:500], reference=leg.reference,
            contact_label=leg.contact_label, contact_id=leg.contact_id, case_contact_id=leg.case_contact_id,
            firm_bank_account_id=leg.firm_bank_account_id, payment_method=leg.payment_method,
            posted_by_user_id=user.id, posted_at=utcnow(), is_approved=True, is_anticipated=False))
    db.flush()
    return pair_id


def reverse_posting(db, *, case_id, pair_id, payload, user):
    require_actor(db, user, case_id)
    if not payload.reason.strip():
        raise HTTPException(400, 'A reversal reason is required')
    # Recheck posting permissions even when replaying an accepted request.
    entries = list(db.scalars(select(LedgerEntry).where(LedgerEntry.pair_id == pair_id)))
    if not entries:
        raise HTTPException(404, 'Posting not found')
    directions = {}
    for leg in entries:
        account = db.get(LedgerAccount, leg.account_id)
        require_actor(db, user, account.case_id)
        if account.case_id != case_id:
            raise HTTPException(404, 'Posting not found on this matter')
        directions[f'{account.account_type.value}_direction'] = 'debit' if leg.direction == LedgerDirection.credit else 'credit'
    assert_may_post_ledger(user, LedgerPostCreate(description='Reversal', amount_pence=entries[0].amount_pence,
                                                **directions), db)
    fingerprint, previous = request_receipt(db, user, 'reverse_posting', payload, pair_id)
    if previous:
        return json.loads(previous.result_json)
    legs = reversal_legs(db, case_id, pair_id, user)
    result_id = compensate(db, legs, user, payload.reason.strip())
    result = {'pair_id': str(result_id), 'reverses_pair_id': str(pair_id)}
    record_receipt(db, user, 'reverse_posting', payload, fingerprint, result_id, result, reverses_id=pair_id)
    log_event(db, actor_user_id=user.id, action='ledger.reverse', entity_type='ledger_pair', entity_id=str(pair_id),
              meta={'case_id': str(case_id), **result, 'reason': payload.reason.strip()})
    return result
