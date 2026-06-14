"""Case invoices: lines stored in DB; pending office posting until approved or voided."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ledger_audit import log_invoice_approve, log_invoice_create, log_invoice_void, log_ledger_post
from app.ledger_service import approve_ledger_pair, delete_ledger_pair_unapproved, get_ledger, post_transaction
from app.case_time_service import mark_time_entries_billed, release_billed_time_entries_for_invoice, resolve_unbilled_time_entries_for_billing
from app.models import Case, CaseInvoice, CaseInvoiceLine, InvoiceSeq, LedgerEntry, User
from app.permission_checks import user_may_approve_invoice
from app.schemas import CaseInvoiceCreate, CaseInvoiceLineOut, CaseInvoiceOut, CaseInvoicesOut, LedgerPostCreate

INV_PENDING = "pending_approval"
INV_APPROVED = "approved"
INV_VOIDED = "voided"


def _next_invoice_number(db: Session) -> str:
    row = db.get(InvoiceSeq, 1)
    if row is None:
        row = InvoiceSeq(id=1, next_num=1)
        db.add(row)
        db.flush()
    n = int(row.next_num)
    row.next_num = n + 1
    db.add(row)
    db.flush()
    return f"INV-{n:07d}"


def list_case_invoices(case_id: uuid.UUID, db: Session) -> CaseInvoicesOut:
    rows = (
        db.execute(
            select(CaseInvoice)
            .where(CaseInvoice.case_id == case_id)
            .order_by(CaseInvoice.created_at.desc())
        )
        .scalars()
        .all()
    )
    out: list[CaseInvoiceOut] = []
    for inv in rows:
        lines = (
            db.execute(select(CaseInvoiceLine).where(CaseInvoiceLine.invoice_id == inv.id))
            .scalars()
            .all()
        )
        cu = db.get(User, inv.credit_user_id) if inv.credit_user_id else None
        credit_name = (cu.display_name or cu.email or "").strip() if cu else None
        out.append(
            CaseInvoiceOut(
                id=inv.id,
                case_id=inv.case_id,
                invoice_number=inv.invoice_number,
                status=inv.status,
                total_pence=int(inv.total_pence),
                payee_name=inv.payee_name,
                credit_user_id=inv.credit_user_id,
                credit_user_display_name=credit_name,
                contact_id=inv.contact_id,
                ledger_pair_id=inv.ledger_pair_id,
                created_by_user_id=inv.created_by_user_id,
                approved_by_user_id=inv.approved_by_user_id,
                approved_at=inv.approved_at,
                voided_at=inv.voided_at,
                created_at=inv.created_at,
                document_file_id=inv.document_file_id,
                lines=[
                    CaseInvoiceLineOut(
                        id=ln.id,
                        line_type=ln.line_type,
                        description=ln.description,
                        amount_pence=int(ln.amount_pence),
                        tax_pence=int(ln.tax_pence),
                        credit_user_id=ln.credit_user_id,
                    )
                    for ln in lines
                ],
            )
        )
    return CaseInvoicesOut(case_id=case_id, invoices=out)


def create_case_invoice(case_id: uuid.UUID, payload: CaseInvoiceCreate, user: User, db: Session) -> CaseInvoiceOut:
    if not payload.lines and not payload.time_entry_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one invoice line or time entry is required.")
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    credit_u = db.get(User, payload.credit_user_id)
    if not credit_u:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Credit user not found.")
    payee_display = (credit_u.display_name or credit_u.email or "").strip()

    time_pairs = resolve_unbilled_time_entries_for_billing(case_id, payload.time_entry_ids, db)

    total = 0
    line_rows: list[CaseInvoiceLine] = []
    time_bill_pairs: list[tuple] = []
    now = datetime.utcnow()
    inv_id = uuid.uuid4()
    inv_num = _next_invoice_number(db)

    for spec in payload.lines:
        ln = CaseInvoiceLine(
            id=uuid.uuid4(),
            invoice_id=inv_id,
            line_type=spec.line_type,
            description=spec.description.strip(),
            amount_pence=spec.amount_pence,
            tax_pence=spec.tax_pence,
            credit_user_id=spec.credit_user_id,
        )
        total += spec.amount_pence + spec.tax_pence
        line_rows.append(ln)

    for tp in time_pairs:
        spec = tp.spec
        ln = CaseInvoiceLine(
            id=uuid.uuid4(),
            invoice_id=inv_id,
            line_type=spec.line_type,
            description=spec.description.strip(),
            amount_pence=spec.amount_pence,
            tax_pence=spec.tax_pence,
            credit_user_id=spec.credit_user_id,
        )
        total += spec.amount_pence + spec.tax_pence
        line_rows.append(ln)
        time_bill_pairs.append((tp.entry, ln))

    if total <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invoice total must be positive.")

    pair_id = post_transaction(
        case_id,
        LedgerPostCreate(
            description=f"Invoice {inv_num} (pending approval)",
            reference=inv_num,
            contact_label=None,
            amount_pence=total,
            client_direction=None,
            office_direction="debit",
        ),
        user,
        db,
        force_unapproved=True,
    )

    inv = CaseInvoice(
        id=inv_id,
        case_id=case_id,
        invoice_number=inv_num,
        status=INV_PENDING,
        ledger_pair_id=pair_id,
        reversal_pair_id=None,
        total_pence=total,
        payee_name=(payload.payee_name.strip() if payload.payee_name else None) or payee_display or None,
        credit_user_id=payload.credit_user_id,
        contact_id=payload.contact_id,
        created_by_user_id=user.id,
        approved_by_user_id=None,
        approved_at=None,
        voided_at=None,
        created_at=now,
    )
    db.add(inv)
    for ln in line_rows:
        db.add(ln)
    db.flush()
    if time_bill_pairs:
        mark_time_entries_billed(db, time_bill_pairs)
        db.flush()
    inv_out = list_case_invoices(case_id, db).invoices[0]
    post_payload = LedgerPostCreate(
        description=f"Invoice {inv_num} (pending approval)",
        reference=inv_num,
        contact_label=None,
        amount_pence=total,
        client_direction=None,
        office_direction="debit",
    )
    log_ledger_post(
        db,
        actor_user_id=user.id,
        case_id=case_id,
        pair_id=pair_id,
        payload=post_payload,
        is_approved=False,
        invoice_number=inv_num,
    )
    log_invoice_create(
        db,
        actor_user_id=user.id,
        case_id=case_id,
        invoice_id=inv_id,
        invoice_number=inv_num,
        total_pence=total,
        pair_id=pair_id,
    )
    return inv_out


def approve_case_invoice(case_id: uuid.UUID, invoice_id: uuid.UUID, user: User, db: Session) -> None:
    if not user_may_approve_invoice(user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to approve invoices.",
        )
    inv = db.get(CaseInvoice, invoice_id)
    if not inv or inv.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if inv.status != INV_PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice is not pending approval.")
    if not inv.ledger_pair_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice has no ledger posting.")

    approve_ledger_pair(case_id, inv.ledger_pair_id, db)
    new_desc = f"Invoice {inv.invoice_number}"
    # Core UPDATE so description / approval are persisted even if ORM instances in the session were stale.
    db.execute(
        update(LedgerEntry)
        .where(LedgerEntry.pair_id == inv.ledger_pair_id)
        .values(description=new_desc, is_approved=True)
    )
    db.flush()
    inv.status = INV_APPROVED
    inv.approved_by_user_id = user.id
    inv.approved_at = datetime.utcnow()
    db.add(inv)
    db.flush()
    log_invoice_approve(
        db,
        actor_user_id=user.id,
        case_id=case_id,
        invoice_id=invoice_id,
        invoice_number=inv.invoice_number,
        total_pence=int(inv.total_pence),
        pair_id=inv.ledger_pair_id,
    )
    case = db.get(Case, case_id)
    if case is not None:
        from app.invoice_document_service import save_invoice_document_to_case

        save_invoice_document_to_case(inv=inv, case=case, actor_user_id=user.id, db=db)


def void_case_invoice(case_id: uuid.UUID, invoice_id: uuid.UUID, user: User, db: Session) -> None:
    if not user_may_approve_invoice(user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to void invoices.",
        )
    inv = db.get(CaseInvoice, invoice_id)
    if not inv or inv.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if inv.status == INV_VOIDED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice already voided.")

    now = datetime.utcnow()
    if inv.status == INV_PENDING:
        if inv.ledger_pair_id:
            delete_ledger_pair_unapproved(case_id, inv.ledger_pair_id, db)
        release_billed_time_entries_for_invoice(invoice_id, db)
        inv.status = INV_VOIDED
        inv.voided_at = now
        db.add(inv)
        db.flush()
        log_invoice_void(
            db,
            actor_user_id=user.id,
            case_id=case_id,
            invoice_id=invoice_id,
            invoice_number=inv.invoice_number,
            total_pence=int(inv.total_pence),
            was_pending=True,
        )
        return

    # Approved: post reversal (office credit) and require office balance check per spec
    if inv.status != INV_APPROVED or not inv.ledger_pair_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot void this invoice.")

    ledger = get_ledger(case_id, db)
    office_bal = ledger.office.balance_pence
    total = int(inv.total_pence)
    # After reversal (office credit), office balance increases by total (less negative DR).
    if office_bal + total > 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Voiding this invoice is not allowed: the office account balance would be above £0.00 "
                f"after reversal (current office balance {office_bal / 100:.2f})."
            ),
        )

    rev_id = post_transaction(
        case_id,
        LedgerPostCreate(
            description=f"Reversal of invoice {inv.invoice_number}",
            reference=inv.invoice_number,
            contact_label=None,
            amount_pence=total,
            client_direction=None,
            office_direction="credit",
        ),
        user,
        db,
    )
    approve_ledger_pair(case_id, rev_id, db)

    release_billed_time_entries_for_invoice(invoice_id, db)
    inv.status = INV_VOIDED
    inv.voided_at = now
    inv.reversal_pair_id = rev_id
    db.add(inv)
    db.flush()
    rev_payload = LedgerPostCreate(
        description=f"Reversal of invoice {inv.invoice_number}",
        reference=inv.invoice_number,
        contact_label=None,
        amount_pence=total,
        client_direction=None,
        office_direction="credit",
    )
    log_ledger_post(
        db,
        actor_user_id=user.id,
        case_id=case_id,
        pair_id=rev_id,
        payload=rev_payload,
        is_approved=True,
        invoice_number=inv.invoice_number,
    )
    log_invoice_void(
        db,
        actor_user_id=user.id,
        case_id=case_id,
        invoice_id=invoice_id,
        invoice_number=inv.invoice_number,
        total_pence=total,
        was_pending=False,
        reversal_pair_id=rev_id,
    )


def list_recent_approved_invoices(
    fee_earner_ids: list[uuid.UUID],
    db: Session,
    *,
    limit: int = 50,
) -> list[dict]:
    """Firm-wide recently approved invoices for the accounts desk."""
    rows = (
        db.execute(
            select(CaseInvoice, Case)
            .join(Case, Case.id == CaseInvoice.case_id)
            .where(
                Case.fee_earner_user_id.in_(fee_earner_ids),
                CaseInvoice.status == INV_APPROVED,
            )
            .order_by(CaseInvoice.approved_at.desc().nullslast(), CaseInvoice.created_at.desc())
            .limit(limit)
        )
        .all()
    )
    out: list[dict] = []
    for inv, case in rows:
        fe = db.get(User, case.fee_earner_user_id)
        fe_name = (fe.display_name or fe.email or "").strip() if fe else ""
        out.append(
            {
                "invoice_id": str(inv.id),
                "case_id": str(case.id),
                "case_number": case.case_number,
                "client_name": case.client_name or "",
                "matter_description": case.title,
                "fee_earner_name": fe_name,
                "invoice_number": inv.invoice_number,
                "approved_at": inv.approved_at.isoformat() if inv.approved_at else None,
                "total_pence": int(inv.total_pence),
                "document_file_id": str(inv.document_file_id) if inv.document_file_id else None,
            }
        )
    return out
