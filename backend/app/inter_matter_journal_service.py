"""Inter-matter client account transfers (journals)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

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
    from_case = db.get(Case, payload.from_case_id)
    to_case = db.get(Case, payload.to_case_id)
    if from_case is None or to_case is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    bank_id = payload.firm_bank_account_id
    if bank_id is None:
        d = default_client_bank(db)
        bank_id = d.id if d else None

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
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return InterMatterJournalOut(
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
