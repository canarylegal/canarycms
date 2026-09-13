"""Ledger service — double-entry posting logic adhering to SAR 2019."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ledger_party import resolve_ledger_party
from app.models import (
    Case,
    CaseInvoice,
    CaseStatus,
    LedgerAccount,
    LedgerAccountType,
    LedgerDirection,
    LedgerEntry,
    User,
)
from app.permission_checks import (
    assert_may_approve_anticipated_ledger,
    assert_may_edit_ledger_pair,
    assert_may_post_anticipated,
    assert_may_post_ledger,
    user_may_approve_ledger,
)
from app.schemas import LedgerAccountSummary, LedgerEntryOut, LedgerOut, LedgerPairUpdate, LedgerPostCreate
from app.timeutil import utcnow

_INVOICE_PENDING = "pending_approval"
_INVOICE_PAIR_LEDGER_MSG = (
    "This posting belongs to a pending invoice. Approve or void it from Invoices — "
    "not via ledger approval."
)


def pending_invoice_for_ledger_pair(db: Session, pair_id: uuid.UUID) -> CaseInvoice | None:
    """Return the pending invoice that owns this ledger pair, if any (CL-08)."""
    return db.execute(
        select(CaseInvoice).where(
            CaseInvoice.ledger_pair_id == pair_id,
            CaseInvoice.status == _INVOICE_PENDING,
        )
    ).scalar_one_or_none()


def raise_if_pending_invoice_owns_pair(db: Session, pair_id: uuid.UUID) -> None:
    if pending_invoice_for_ledger_pair(db, pair_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_INVOICE_PAIR_LEDGER_MSG,
        )


@dataclass(frozen=True)
class LedgerPostResult:
    pair_id: uuid.UUID
    is_approved: bool
    is_anticipated: bool


def _get_or_create_accounts(case_id: uuid.UUID, db: Session, *, for_update: bool = False) -> dict[str, LedgerAccount]:
    """Return {account_type: LedgerAccount}, creating rows if they don't exist yet.

    When ``for_update`` is true, locks account rows (``SELECT … FOR UPDATE``) so concurrent
    approved posts cannot both pass the SAR deficit check.
    """

    def _load() -> dict[str, LedgerAccount]:
        q = select(LedgerAccount).where(LedgerAccount.case_id == case_id)
        if for_update:
            q = q.with_for_update()
        rows = db.execute(q).scalars().all()
        return {r.account_type.value: r for r in rows}

    by_type = _load()
    missing = [atype for atype in (LedgerAccountType.client, LedgerAccountType.office) if atype.value not in by_type]
    if missing:
        now = utcnow()
        try:
            with db.begin_nested():
                for atype in missing:
                    db.add(
                        LedgerAccount(
                            id=uuid.uuid4(),
                            case_id=case_id,
                            account_type=atype,
                            created_at=now,
                        )
                    )
                db.flush()
        except IntegrityError:
            pass
        by_type = _load()
        if any(atype.value not in by_type for atype in (LedgerAccountType.client, LedgerAccountType.office)):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not initialise ledger accounts for this matter.",
            )
    return by_type


def _balance(account_id: uuid.UUID, db: Session, *, approved_only: bool = True) -> int:
    """Net balance in pence: sum(credits) - sum(debits)."""
    signed = case(
        (LedgerEntry.direction == LedgerDirection.credit, LedgerEntry.amount_pence),
        else_=-LedgerEntry.amount_pence,
    )
    q = select(func.coalesce(func.sum(signed), 0)).where(LedgerEntry.account_id == account_id)
    if approved_only:
        q = q.where(LedgerEntry.is_approved.is_(True))
    return int(db.execute(q).scalar_one())


def _projected_client_balance_after_debit(
    *,
    current_balance: int,
    amount_pence: int,
    client_direction: str | None,
) -> int:
    if client_direction == "debit":
        return current_balance - amount_pence
    if client_direction == "credit":
        return current_balance + amount_pence
    return current_balance


def _reject_client_deficit(balance: int) -> None:
    if balance < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Posting rejected: client account would go into deficit "
                f"(balance would be £{abs(balance)/100:.2f} DR). "
                "SAR 2019 prohibits a debit balance on a client account."
            ),
        )


def _maybe_activate_quote_case(db: Session, case_id: uuid.UUID) -> None:
    """First approved ledger activity on a quote matter promotes it to Active (open)."""
    case = db.get(Case, case_id)
    if case is None or case.status != CaseStatus.quote:
        return
    case.status = CaseStatus.open
    case.updated_at = utcnow()
    db.add(case)


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

    Anticipated postings require post anticipated permission; they stay unapproved and off
    balances until a user with post rights on each leg approves.

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
        assert_may_post_anticipated(user, db)
        is_anticipated = True
        is_approved = False
    else:
        assert_may_post_ledger(user, payload, db)
        is_anticipated = False
        is_approved = True

    party = resolve_ledger_party(case_id, payload, db)

    accounts = _get_or_create_accounts(case_id, db, for_update=is_approved)
    if is_approved and payload.client_direction:
        current = _balance(accounts["client"].id, db, approved_only=True)
        projected = _projected_client_balance_after_debit(
            current_balance=current,
            amount_pence=payload.amount_pence,
            client_direction=payload.client_direction,
        )
        _reject_client_deficit(projected)

    pair_id = uuid.uuid4()
    now = utcnow()
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

    if is_approved:
        _maybe_activate_quote_case(db, case_id)

    return LedgerPostResult(pair_id=pair_id, is_approved=is_approved, is_anticipated=is_anticipated)


def _ledger_pair_legs(case_id: uuid.UUID, pair_id: uuid.UUID, db: Session) -> tuple[dict[str, LedgerAccount], list[LedgerEntry]]:
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
    return accounts, legs


def _pair_directions(legs: list[LedgerEntry], accounts: dict[str, LedgerAccount]) -> tuple[str | None, str | None]:
    client_direction = None
    office_direction = None
    for e in legs:
        if e.account_id == accounts["client"].id:
            client_direction = e.direction.value
        elif e.account_id == accounts["office"].id:
            office_direction = e.direction.value
    return client_direction, office_direction


def update_ledger_pair_unapproved(
    case_id: uuid.UUID,
    pair_id: uuid.UUID,
    payload: LedgerPairUpdate,
    user: User,
    db: Session,
) -> None:
    """Edit amount, description, reference, or anticipated date before approval."""
    raise_if_pending_invoice_owns_pair(db, pair_id)
    accounts, legs = _ledger_pair_legs(case_id, pair_id, db)
    if not legs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Posting not found")
    if any(e.is_approved for e in legs):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approved postings cannot be edited")

    client_direction, office_direction = _pair_directions(legs, accounts)
    is_anticipated = any(e.is_anticipated for e in legs)
    poster_user_id = legs[0].posted_by_user_id
    assert_may_edit_ledger_pair(
        user,
        client_direction=client_direction,
        office_direction=office_direction,
        is_anticipated=is_anticipated,
        db=db,
        posted_by_user_id=poster_user_id,
    )

    if payload.anticipated_for_date is not None and not is_anticipated:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="anticipated_for_date applies only to anticipated postings",
        )

    for e in legs:
        if payload.amount_pence is not None:
            e.amount_pence = payload.amount_pence
        if payload.description is not None:
            e.description = payload.description
        if payload.reference is not None:
            e.reference = payload.reference or None
        if payload.anticipated_for_date is not None and e.is_anticipated:
            e.anticipated_for_date = payload.anticipated_for_date
        db.add(e)
    db.flush()
    if is_anticipated and poster_user_id is not None and user.id != poster_user_id:
        from app.staff_workflow_notifications import notify_anticipated_payment_amended

        notify_anticipated_payment_amended(
            db,
            case_id=case_id,
            actor=user,
            poster_user_id=poster_user_id,
            description=(legs[0].description or "").strip(),
            amount_pence=int(legs[0].amount_pence),
            reference=legs[0].reference,
        )


def reject_ledger_pair_unapproved(
    case_id: uuid.UUID,
    pair_id: uuid.UUID,
    user: User,
    db: Session,
    *,
    reject_comment: str | None = None,
) -> None:
    """Remove an unapproved or anticipated posting (reject draft)."""
    raise_if_pending_invoice_owns_pair(db, pair_id)
    accounts, legs = _ledger_pair_legs(case_id, pair_id, db)
    if not legs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Posting not found")
    if any(e.is_approved for e in legs):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approved postings cannot be rejected")

    client_direction, office_direction = _pair_directions(legs, accounts)
    is_anticipated = any(e.is_anticipated for e in legs)
    poster_user_id = legs[0].posted_by_user_id
    description = (legs[0].description or "").strip()
    amount_pence = int(legs[0].amount_pence)
    reference = legs[0].reference
    assert_may_edit_ledger_pair(
        user,
        client_direction=client_direction,
        office_direction=office_direction,
        is_anticipated=is_anticipated,
        db=db,
        posted_by_user_id=poster_user_id,
        for_reject=True,
    )
    for e in legs:
        db.delete(e)
    db.flush()
    if is_anticipated:
        from app.staff_workflow_notifications import notify_anticipated_payment_rejected

        notify_anticipated_payment_rejected(
            db,
            case_id=case_id,
            poster_user_id=poster_user_id,
            actor=user,
            description=description,
            amount_pence=amount_pence,
            reference=reference,
            comment=reject_comment,
        )


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


def approve_ledger_pair(
    case_id: uuid.UUID,
    pair_id: uuid.UUID,
    user: User,
    db: Session,
    *,
    invoice_workflow: bool = False,
) -> None:
    """Approve a pending posting; anticipated rows become actual and affect balances.

    When ``invoice_workflow`` is True (called from invoice approval), payment-approve
    permission is not required and an already-approved pair is a no-op so concurrent
    retries can finish the invoice row without a 400/500 (CL-08).
    """
    if not invoice_workflow:
        raise_if_pending_invoice_owns_pair(db, pair_id)

    accounts = _get_or_create_accounts(case_id, db, for_update=True)
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
        if invoice_workflow:
            return
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Posting is already approved")

    was_anticipated = any(e.is_anticipated for e in legs)
    poster_user_id = legs[0].posted_by_user_id
    snap_description = (legs[0].description or "").strip()
    snap_amount_pence = int(legs[0].amount_pence)
    snap_reference = legs[0].reference

    client_direction = None
    office_direction = None
    for e in legs:
        if e.account_id == accounts["client"].id:
            client_direction = e.direction.value
        elif e.account_id == accounts["office"].id:
            office_direction = e.direction.value

    if invoice_workflow:
        # Invoice permission already checked by approve_case_invoice.
        pass
    elif any(e.is_anticipated for e in legs):
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

    if client_direction:
        current = _balance(accounts["client"].id, db, approved_only=True)
        projected = _projected_client_balance_after_debit(
            current_balance=current,
            amount_pence=snap_amount_pence,
            client_direction=client_direction,
        )
        if projected < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Approving this posting would put the client account into deficit "
                    f"(balance would be £{abs(projected)/100:.2f} DR)."
                ),
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

    if was_anticipated:
        from app.staff_workflow_notifications import notify_anticipated_payment_approved

        notify_anticipated_payment_approved(
            db,
            case_id=case_id,
            poster_user_id=poster_user_id,
            actor=user,
            description=snap_description,
            amount_pence=snap_amount_pence,
            reference=snap_reference,
        )

    _maybe_activate_quote_case(db, case_id)
