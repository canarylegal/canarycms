"""Xero-oriented office journal CSV export (manual import path)."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Case,
    CaseInvoice,
    LedgerAccount,
    LedgerAccountType,
    LedgerEntry,
    User,
    XeroIntegrationSettings,
    XeroJournalExport,
)


def get_xero_settings(db: Session) -> XeroIntegrationSettings:
    row = db.get(XeroIntegrationSettings, 1)
    if row is None:
        row = XeroIntegrationSettings(id=1, enabled=False)
        db.add(row)
        db.flush()
    return row


def update_xero_settings(db: Session, **fields) -> XeroIntegrationSettings:
    row = get_xero_settings(db)
    for k, v in fields.items():
        if v is not None and hasattr(row, k):
            setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.flush()
    return row


def build_xero_journal_csv(
    db: Session,
    *,
    period_from: date,
    period_to: date,
    settings: XeroIntegrationSettings,
) -> tuple[bytes, int]:
    """Export approved office legs as a simple Xero Manual Journal CSV."""
    income = (settings.office_income_code or "200").strip()
    bank = (settings.office_bank_code or "090").strip()
    vat = (settings.vat_code or "820").strip()
    disb = (settings.disbursement_code or "310").strip()

    start = datetime(period_from.year, period_from.month, period_from.day, tzinfo=timezone.utc)
    end = datetime(period_to.year, period_to.month, period_to.day, 23, 59, 59, tzinfo=timezone.utc)

    q = (
        select(LedgerEntry, Case)
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .join(Case, Case.id == LedgerAccount.case_id)
        .where(
            LedgerAccount.account_type == LedgerAccountType.office,
            LedgerEntry.is_approved.is_(True),
            LedgerEntry.posted_at >= start,
            LedgerEntry.posted_at <= end,
        )
        .order_by(LedgerEntry.posted_at)
    )

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "Narration",
            "Date",
            "Description",
            "AccountCode",
            "TaxType",
            "Debit",
            "Credit",
            "TrackingName1",
            "TrackingOption1",
        ]
    )
    count = 0
    for e, case in db.execute(q).all():
        matter = case.case_number or str(case.id)[:8]
        narr = f"{matter} — {e.description}"[:200]
        dt = e.posted_at.date().isoformat()
        amt = f"{e.amount_pence / 100:.2f}"
        # Heuristic: invoice-like office debit → income; credit → bank/receipt
        desc_l = (e.description or "").lower()
        if "vat" in desc_l:
            code = vat
        elif "disburs" in desc_l or "search" in desc_l:
            code = disb
        elif e.direction.value == "debit":
            code = income
        else:
            code = bank
        debit = amt if e.direction.value == "debit" else ""
        credit = amt if e.direction.value == "credit" else ""
        w.writerow([narr, dt, e.description, code, "No VAT", debit, credit, "Matter", matter])
        count += 1

    # Also include approved invoices as a control section if none matched (still list totals)
    invoices = db.execute(
        select(CaseInvoice).where(
            CaseInvoice.status == "approved",
            CaseInvoice.approved_at.is_not(None),
            CaseInvoice.approved_at >= start,
            CaseInvoice.approved_at <= end,
        )
    ).scalars().all()
    for inv in invoices:
        # Already reflected via ledger pair usually; skip if pair exists
        if inv.ledger_pair_id:
            continue
        matter_case = db.get(Case, inv.case_id)
        matter = (matter_case.case_number if matter_case else "") or str(inv.case_id)[:8]
        amt = f"{inv.total_pence / 100:.2f}"
        dt = (inv.approved_at or inv.created_at).date().isoformat()
        w.writerow(
            [
                f"Invoice {inv.invoice_number}",
                dt,
                f"Invoice {inv.invoice_number}",
                income,
                "No VAT",
                amt,
                "",
                "Matter",
                matter,
            ]
        )
        count += 1

    return buf.getvalue().encode("utf-8"), count


def create_xero_export(
    db: Session,
    *,
    actor: User,
    period_from: date,
    period_to: date,
) -> XeroJournalExport:
    if period_to < period_from:
        raise HTTPException(status_code=400, detail="period_to must be on or after period_from")
    settings = get_xero_settings(db)
    content, count = build_xero_journal_csv(
        db, period_from=period_from, period_to=period_to, settings=settings
    )
    filename = f"xero-journals-{period_from.isoformat()}_{period_to.isoformat()}.csv"
    row = XeroJournalExport(
        id=uuid.uuid4(),
        period_from=period_from,
        period_to=period_to,
        generated_by_user_id=actor.id,
        generated_at=datetime.now(timezone.utc),
        filename=filename,
        content=content,
        content_type="text/csv",
        row_count=count,
    )
    db.add(row)
    db.flush()
    return row


def list_xero_exports(db: Session, *, limit: int = 24) -> list[XeroJournalExport]:
    return list(
        db.execute(select(XeroJournalExport).order_by(XeroJournalExport.generated_at.desc()).limit(limit))
        .scalars()
        .all()
    )


def get_xero_export(db: Session, export_id: uuid.UUID) -> XeroJournalExport:
    row = db.get(XeroJournalExport, export_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    return row
