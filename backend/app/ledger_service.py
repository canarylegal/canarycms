"""Ledger service — double-entry posting logic adhering to SAR 2019."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger_party import resolve_ledger_party
from app.models import LedgerAccount, LedgerAccountType, LedgerDirection, LedgerEntry, User
from app.permission_checks import (
    assert_may_approve_anticipated_ledger,
    assert_may_post_ledger,
    user_may_approve_ledger,
)
from app.schemas import LedgerAccountSummary, LedgerEntryOut, LedgerOut, LedgerPostCreate


@dataclass(frozen=True)
class LedgerPostResult:
    pair_id: uuid.UUID
    is_approved: bool
    is_anticipated: bool


def _get_or_create_accounts(case_id: uuid.UUID, db: Session) -> dict[str, LedgerAccount]:
    """Return {account_type: LedgerAccount}, creating rows if they don't exist yet."""
    rows = (
        db.execute(
            select(LedgerAccount).where(LedgerAccount.case_id == case_id)
        )
        .scalars()
        .all()
    )
    by_type: dict[str, LedgerAccount] = {r.account_type.value: r for r in rows}
    changed = False
    for atype in (LedgerAccountType.client, LedgerAccountType.office):
        if atype.value not in by_type:
            acc = LedgerAccount(
                id=uuid.uuid4(),
                case_id=case_id,
                account_type=atype,
                created_at=datetime.utcnow(),
            )
            db.add(acc)
            by_type[atype.value] = acc
            changed = True
    if changed:
        db.flush()
    return by_type


def _balance(account_id: uuid.UUID, db: Session, *, approved_only: bool = True) -> int:
    """Net balance in pence: sum(credits) - sum(debits)."""
    q = select(LedgerEntry).where(LedgerEntry.account_id == account_id)
    if approved_only:
        q = q.where(LedgerEntry.is_approved.is_(True))
    entries = db.execute(q).scalars().all()
    total = 0
    for e in entries:
        if e.direction == LedgerDirection.credit:
            total += e.amount_pence
        else:
            total -= e.amount_pence
    return total


def post_transaction(
    case_id: uuid.UUID,
    payload: LedgerPostCreate,
    user: User,
    db: Session,
    *,
    force_unapproved: bool = False,
) -> LedgerPostResult:
    """
    Create a double-entry posting.

    Anticipated postings may be created by any user with matter access; they stay
    unapproved and off balances until a user with post rights on each leg approves.

    Actual postings require client/office post permission on each affected leg and
    take effect immediately (approved).
    """
    if not payload.client_direction and not payload.office_direction:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of client_direction or office_direction is required.",
        )

    if force_unapproved:
        is_anticipated = False
        is_approved = False
    elif payload.anticipated:
        is_anticipated = True
        is_approved = False
    else:
        assert_may_post_ledger(user, payload, db)
        is_anticipated = False
        is_approved = True

    party = resolve_ledger_party(case_id, payload, db)

    accounts = _get_or_create_accounts(case_id, db)
    pair_id = uuid.uuid4()
    now = datetime.utcnow()
    anticipated_for_date = payload.anticipated_for_date if is_anticipated else None
    legs: list[LedgerEntry] = []

    if payload.client_direction:
        legs.append(
            LedgerEntry(
                id=uuid.uuid4(),
                account_id=accounts["client"].id,
                pair_id=pair_id,
                direction=LedgerDirection(payload.client_direction),
                amount_pence=payload.amount_pence,
                description=payload.description,
                reference=payload.reference,
                contact_label=party.contact_label,
                case_contact_id=party.case_contact_id,
                contact_id=party.contact_id,
                posted_by_user_id=user.id,
                posted_at=now,
                is_approved=is_approved,
                is_anticipated=is_anticipated,
                anticipated_for_date=anticipated_for_date,
            )
        )

    if payload.office_direction:
        legs.append(
            LedgerEntry(
                id=uuid.uuid4(),
                account_id=accounts["office"].id,
                pair_id=pair_id,
                direction=LedgerDirection(payload.office_direction),
                amount_pence=payload.amount_pence,
                description=payload.description,
                reference=payload.reference,
                contact_label=party.contact_label,
                case_contact_id=party.case_contact_id,
                contact_id=party.contact_id,
                posted_by_user_id=user.id,
                posted_at=now,
                is_approved=is_approved,
                is_anticipated=is_anticipated,
                anticipated_for_date=anticipated_for_date,
            )
        )

    for leg in legs:
        db.add(leg)
    db.flush()

    # SAR no-deficit check on client account (approved postings only affect balance).
    client_balance = _balance(accounts["client"].id, db, approved_only=True)
    if client_balance < 0:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Posting rejected: client account would go into deficit "
                f"(balance would be £{abs(client_balance)/100:.2f} DR). "
                "SAR 2019 prohibits a debit balance on a client account."
            ),
        )

    return LedgerPostResult(pair_id=pair_id, is_approved=is_approved, is_anticipated=is_anticipated)


def delete_ledger_pair_unapproved(case_id: uuid.UUID, pair_id: uuid.UUID, db: Session) -> None:
    """Remove both legs of an unapproved posting (e.g. void draft invoice)."""
    accounts = _get_or_create_accounts(case_id, db)
    aid = {accounts["client"].id, accounts["office"].id}
    legs = (
        db.execute(
            select(LedgerEntry).where(
                LedgerEntry.pair_id == pair_id,
                LedgerEntry.account_id.in_(aid),
            )
        )
        .scalars()
        .all()
    )
    if not legs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Posting not found")
    if any(e.is_approved for e in legs):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove an approved posting; use a reversal instead.",
        )
    for e in legs:
        db.delete(e)
    db.flush()


def get_ledger(case_id: uuid.UUID, db: Session) -> LedgerOut:
    accounts = _get_or_create_accounts(case_id, db)

    all_entries = (
        db.execute(
            select(LedgerEntry)
            .where(
                LedgerEntry.account_id.in_(
                    [accounts["client"].id, accounts["office"].id]
                )
            )
            .order_by(LedgerEntry.posted_at)
        )
        .scalars()
        .all()
    )

    account_id_to_type = {
        accounts["client"].id: "client",
        accounts["office"].id: "office",
    }

    entry_outs: list[LedgerEntryOut] = []
    for e in all_entries:
        entry_outs.append(
            LedgerEntryOut(
                id=e.id,
                pair_id=e.pair_id,
                account_type=account_id_to_type[e.account_id],
                direction=e.direction.value,
                amount_pence=e.amount_pence,
                description=e.description,
                reference=e.reference,
                contact_label=e.contact_label,
                case_contact_id=e.case_contact_id,
                contact_id=e.contact_id,
                posted_by_user_id=e.posted_by_user_id,
                posted_at=e.posted_at,
                is_approved=e.is_approved,
                is_anticipated=e.is_anticipated,
                anticipated_for_date=e.anticipated_for_date,
            )
        )

    client_balance = _balance(accounts["client"].id, db, approved_only=True)
    office_balance = _balance(accounts["office"].id, db, approved_only=True)

    return LedgerOut(
        entries=entry_outs,
        client=LedgerAccountSummary(account_type="client", balance_pence=client_balance),
        office=LedgerAccountSummary(account_type="office", balance_pence=office_balance),
    )


def approve_ledger_pair(case_id: uuid.UUID, pair_id: uuid.UUID, user: User, db: Session) -> None:
    """Approve a pending posting; anticipated rows become actual and affect balances."""
    accounts = _get_or_create_accounts(case_id, db)
    aid = {accounts["client"].id, accounts["office"].id}
    legs = (
        db.execute(
            select(LedgerEntry).where(
                LedgerEntry.pair_id == pair_id,
                LedgerEntry.account_id.in_(aid),
            )
        )
        .scalars()
        .all()
    )
    if not legs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Posting not found")
    if any(e.account_id not in aid for e in legs):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid posting")
    if any(e.is_approved for e in legs):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Posting is already approved")

    client_direction = None
    office_direction = None
    for e in legs:
        if e.account_id == accounts["client"].id:
            client_direction = e.direction.value
        elif e.account_id == accounts["office"].id:
            office_direction = e.direction.value

    if any(e.is_anticipated for e in legs):
        assert_may_approve_anticipated_ledger(
            user,
            client_direction=client_direction,
            office_direction=office_direction,
            db=db,
        )
    elif not user_may_approve_ledger(user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to approve ledger postings.",
        )

    for e in legs:
        e.is_approved = True
        e.is_anticipated = False
        e.anticipated_for_date = None
    db.flush()

    # Invoice drafts (and similar) store this suffix until approved; strip when approving from the ledger.
    pending_suffix = " (pending approval)"
    for e in legs:
        if e.description and pending_suffix in e.description:
            stripped = e.description.replace(pending_suffix, "").strip()
            if stripped:
                e.description = stripped
            db.add(e)
    db.flush()

    client_balance = _balance(accounts["client"].id, db, approved_only=True)
    if client_balance < 0:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Approving this posting would put the client account into deficit "
                f"(balance would be £{abs(client_balance)/100:.2f} DR)."
            ),
        )
