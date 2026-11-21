"""Inter-matter client account transfers (journals)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.bank_integrity import require_banking
from app.ledger_integrity import lock_matters, record_receipt, request_receipt
from app.ledger_operations import require_actor
from app.permission_checks import assert_may_post_ledger
from app.bank_accounts_service import default_client_bank
from app.ledger_service import post_transaction
from app.models import Case, InterMatterJournal, User
from app.schemas import LedgerPostCreate
from app.schemas.bank import InterMatterJournalCreate, InterMatterJournalOut


def create_inter_matter_journal(
    db: Session,
    *,
    payload: InterMatterJournalCreate,
    user: User,
) -> InterMatterJournalOut:
    require_banking(user, db)
    require_actor(db, user, payload.from_case_id, payload.to_case_id)
    assert_may_post_ledger(user, LedgerPostCreate(description=payload.description,
        amount_pence=payload.amount_pence, client_direction='debit'), db)
    fingerprint, previous = request_receipt(db, user, 'transfer', payload, '')
    if previous:
        return InterMatterJournalOut.model_validate_json(previous.result_json)
    lock_matters(db, payload.from_case_id, payload.to_case_id)
    from_case = db.get(Case, payload.from_case_id)
    to_case = db.get(Case, payload.to_case_id)
    if from_case is None or to_case is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    bank_id = payload.firm_bank_account_id
    if bank_id is None:
        d = default_client_bank(db)
        bank_id = d.id if d else None

    from app.timeutil import utcnow
    effective_at = utcnow()
    desc = payload.description.strip()
    from_result = post_transaction(
        payload.from_case_id,
        LedgerPostCreate(
            description=f"Transfer to {to_case.case_number or to_case.id}: {desc}"[:500],
            reference=payload.reference,
            amount_pence=payload.amount_pence,
            client_direction="debit",
            firm_bank_account_id=bank_id,
            payment_method="journal",
            contact_label="N/A",
        ),
        user,
        db,
        effective_at=effective_at,
    )
    to_result = post_transaction(
        payload.to_case_id,
        LedgerPostCreate(
            description=f"Transfer from {from_case.case_number or from_case.id}: {desc}"[:500],
            reference=payload.reference,
            amount_pence=payload.amount_pence,
            client_direction="credit",
            firm_bank_account_id=bank_id,
            payment_method="journal",
            contact_label="N/A",
        ),
        user,
        db,
        effective_at=effective_at,
    )
    row = InterMatterJournal(
        id=uuid.uuid4(),
        from_case_id=payload.from_case_id,
        to_case_id=payload.to_case_id,
        firm_bank_account_id=bank_id,
        amount_pence=payload.amount_pence,
        description=desc,
        from_pair_id=from_result.pair_id,
        to_pair_id=to_result.pair_id,
        created_by_user_id=user.id,
        created_at=effective_at,
    )
    db.add(row)
    db.flush()
    result = InterMatterJournalOut(
        id=row.id,
        from_case_id=row.from_case_id,
        to_case_id=row.to_case_id,
        firm_bank_account_id=row.firm_bank_account_id,
        amount_pence=row.amount_pence,
        description=row.description,
        from_pair_id=row.from_pair_id,
        to_pair_id=row.to_pair_id,
        created_at=row.created_at,
    )

    record_receipt(db, user, 'transfer', payload, fingerprint, row.id, result.model_dump(mode='json'))
    log_event(db, actor_user_id=user.id, action='ledger.transfer', entity_type='inter_matter_journal',
              entity_id=str(row.id), meta=result.model_dump(mode='json'))
    return result


def list_inter_matter_journals(db: Session, *, limit: int = 100) -> list[InterMatterJournalOut]:
    rows = db.execute(
        select(InterMatterJournal).order_by(InterMatterJournal.created_at.desc()).limit(limit)
    ).scalars().all()
    return [
        InterMatterJournalOut(
            id=r.id,
            from_case_id=r.from_case_id,
            to_case_id=r.to_case_id,
            firm_bank_account_id=r.firm_bank_account_id,
            amount_pence=r.amount_pence,
            description=r.description,
            from_pair_id=r.from_pair_id,
            to_pair_id=r.to_pair_id,
            created_at=r.created_at,
        )
        for r in rows
    ]


def reverse_inter_matter_journal(db, *, journal_id, payload, user):
    from sqlalchemy import or_
    from app.models import LedgerOperation
    from app.ledger_integrity import lock_operation
    from app.ledger_operations import reversal_legs, compensate

    require_banking(user, db)
    row = db.get(InterMatterJournal, journal_id)
    if row is None:
        raise HTTPException(404, 'Journal not found')
    require_actor(db, user, row.from_case_id, row.to_case_id)
    assert_may_post_ledger(user, LedgerPostCreate(description='Reversal',
        amount_pence=row.amount_pence, client_direction='debit'), db)
    if not payload.reason.strip():
        raise HTTPException(400, 'A reversal reason is required')
    fingerprint, previous = request_receipt(db, user, 'reverse_transfer', payload, journal_id)
    if previous:
        return InterMatterJournalOut.model_validate_json(previous.result_json)
    lock_operation(db, 582013722, str(journal_id))
    lock_matters(db, row.from_case_id, row.to_case_id)
    if db.scalar(select(LedgerOperation.id).where(LedgerOperation.kind == 'reverse_transfer', or_(
            LedgerOperation.reverses_id == journal_id, LedgerOperation.result_id == journal_id)).limit(1)):
        raise HTTPException(409, 'This journal was already reversed or is a reversal')
    source = reversal_legs(db, row.from_case_id, row.from_pair_id, user, journal_id=journal_id)
    destination = reversal_legs(db, row.to_case_id, row.to_pair_id, user, journal_id=journal_id)
    if (len(source) != 1 or len(destination) != 1 or source[0].direction.value != 'debit'
            or destination[0].direction.value != 'credit'
            or any(leg.amount_pence != row.amount_pence or leg.firm_bank_account_id != row.firm_bank_account_id
                   for leg in source + destination)):
        raise HTTPException(409, 'Journal legs are inconsistent; review before reversing')
    now = datetime.now(timezone.utc)
    reverse = InterMatterJournal(id=uuid.uuid4(), from_case_id=row.to_case_id, to_case_id=row.from_case_id,
        firm_bank_account_id=row.firm_bank_account_id, amount_pence=row.amount_pence,
        description=f'Reversal: {payload.reason.strip()}'[:500],
        from_pair_id=compensate(db, destination, user, payload.reason.strip(), effective_at=now),
        to_pair_id=compensate(db, source, user, payload.reason.strip(), effective_at=now), created_by_user_id=user.id, created_at=now)
    db.add(reverse)
    db.flush()
    result = InterMatterJournalOut.model_validate(reverse, from_attributes=True)
    record_receipt(db, user, 'reverse_transfer', payload, fingerprint, reverse.id,
                   result.model_dump(mode='json'), reverses_id=journal_id)
    log_event(db, actor_user_id=user.id, action='ledger.transfer.reverse', entity_type='inter_matter_journal',
              entity_id=str(journal_id), meta={**result.model_dump(mode='json'), 'reason': payload.reason.strip()})
    return result
